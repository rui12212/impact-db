from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.config import MODEL_ASK
from v2_app.core.extract import HISTORY_LAST_N, format_history
from v2_app.core.llm import complete_json

# 必須が埋まったあとに聞く回数（2026-10-13）。
#
# もとは2回、LLMに掘り下げさせていたが実機でくどかった
# （「その時どんな行動が見られましたか」を2回続けられる）。
# **1回だけ、ただしLLMに作らせる。** 固定文は味気ないため。
MAX_FOLLOWUP = 1

# LLMが落ちた時のフォールバック。無言にしないため。
# ⚠️ こちらにも礼を入れる。LLMが落ちた時だけ素っ気なくなるのを避ける
FOLLOWUP_EN = (
    "Thank you for taking the time to record this. "
    "Anything else you learned or noticed?"
)
FOLLOWUP_KM = (
    "អរគុណសម្រាប់ការចំណាយពេលកត់ត្រារឿងនេះ។ "
    "មានអ្វីផ្សេងទៀតដែលអ្នកបានរៀន ឬកត់សម្គាល់ទេ?"
)


SYSTEM_FIELD = """You are helping a teacher record a reflection on their own teaching.

Ask about ONE missing item, as a natural question in conversation.

Rules:
- Write the SAME question twice: once in English, once in Khmer.
- NEVER use Japanese or any other language.
- One short sentence each. No preamble, no explanation.
- Do NOT sound like a form. Ask as a person would.
- Do NOT give advice. Just ask.
"""

# 先生が**文字で書いた**場合。その内容を読んで、考えを一歩進める問い。
SYSTEM_FOLLOWUP_TEXT = """You are helping a teacher think a little further about
what they just wrote about their own teaching.

Read what they wrote and ask ONE question that takes their own thought forward.

Rules:
- Write the SAME text twice: once in English, once in Khmer.
- NEVER use Japanese or any other language.
- **Start with a short thanks for taking the time to record this**, then ask
  the question. Keep the thanks to a few words and vary the wording.
- Thank them ONCE. The thanks is for the act of recording, never a
  compliment about the lesson or about the teacher.
- Two short sentences each at most.
- Build on their own words. Refer to something specific they wrote.
- Ask what they noticed, or why they think it happened.
- Do NOT give advice. Do NOT evaluate or judge what they did.
- Do NOT ask about anything already covered in the conversation.
- If there is genuinely nothing more to ask, set both fields to null.
"""

# 先生が**写真や動画を送った**場合。中身は見えないので、
# 「それについて付け加えたいこと」を聞く。
SYSTEM_FOLLOWUP_MEDIA = """A teacher has just sent a photo or a video from their
own lesson. **You cannot see it.**

Ask ONE short question that invites them to say something about it.

Rules:
- Write the SAME text twice: once in English, once in Khmer.
- NEVER use Japanese or any other language.
- **Start with a short thanks for sharing it**, then ask the question.
  Keep the thanks to a few words and vary the wording.
- Thank them ONCE. The thanks is for the act of recording, never a
  compliment about the lesson or about the teacher.
- Two short sentences each at most.
- Ask what it shows, or why they chose to record that moment.
- Do NOT pretend you can see it. Do NOT describe it.
- Do NOT give advice. Do NOT evaluate or judge what they did.
- If they have already explained it in the conversation, set both fields to null.
"""


async def make_question(
    fields: List[flow.Field],
    filled: Dict[str, Any],
    history: List[Dict[str, str]],
    ask_count: int,
    *,
    kind: str = "text",
    model: Optional[str] = None,
) -> Optional[str]:
    """次の問いかけ。もう聞くことがなければ None。

    kind は直前に先生が送ったものの種類（text / voice / photo / video /
    document）。**写真や動画なら「それについて付け加えたいこと」を聞き、
    文字なら内容を読んで考えを一歩進める問いを聞く**（2026-10-13）。
    """
    field = flow.next_field(fields, filled)
    if field is not None:
        # 足りない項目は schema.py の固定文で聞く（LLMに言い換えさせない）
        return await _ask_field(field, history, model)

    if ask_count < MAX_FOLLOWUP:
        return await _ask_followup(fields, filled, history, kind, model)

    return None


# 英語とクメール語を**1回の呼び出しで両方**作る（2026-10-13決定）。
# 英語で作ってから翻訳すると呼び出しが2回になり、音声の50秒にさらに
# 5〜10秒乗る。1回で両方出せば速度は変わらない。
#
# 両方出す理由: クメール語の先生に英語で返る事故が実機で起きた。
# 併記にすれば言語判定に依存しない（UI文言と同じ方針）。
SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "en": {"type": ["string", "null"]},
        "km": {"type": ["string", "null"]},
    },
    "required": ["en", "km"],
    "additionalProperties": False,
}


def _join(result: Dict[str, Any]) -> str:
    """{en, km} を1通にまとめる。片方しか無ければそれだけ返す。"""
    en = (result.get("en") or "").strip()
    km = (result.get("km") or "").strip()
    if en and km:
        return f"{en}\n{km}"
    return en or km


async def _ask_field(field: flow.Field, history:List[Dict[str, str]], model:Optional[str]) -> str:
    """足りない項目を聞く。**schema.py に書いた固定の文を返す。**

    ⚠️ LLMを使わない（2026-10-13変更）。LLMに言い回しを作らせると
    勝手に言い換える。実機では「What kind of learnings did you have?」が
    「What will you change next time?」になり、写真だけ送った先生に
    的外れな質問が出た。

    文面は schema.py で完全に制御する。速くもなる（LLMを待たない）。
    SYSTEM_FIELD は残してあるが使っていない（→ v2-todo.md A-11）。
    """
    en = (field.get("question") or "").strip()
    km = (field.get("question_km") or "").strip()
    return f"{en}\n{km}" if km else en


async def _ask_followup(
    fields: List[flow.Field],
    filled: Dict[str, Any],
    history: List[Dict[str, str]],
    kind: str,
    model: Optional[str],
) -> Optional[str]:
    """必須が埋まったあとに1回だけ聞く。LLMに作らせる。

    直前に来たものの種類でプロンプトを分ける。
      写真・動画 → それについて付け加えたいことを聞く（中身は見えない）
      文字・音声 → 内容を読んで、考えを一歩進める問いを聞く

    LLMが落ちたら固定文に落とす（無言にしない）。
    """
    is_media = kind in ("photo", "video", "document")
    system = SYSTEM_FOLLOWUP_MEDIA if is_media else SYSTEM_FOLLOWUP_TEXT

    user = (
        f"[Conversation so far]\n{format_history(history[-HISTORY_LAST_N:])}\n\n"
        f"[What has been recorded]\n{flow.render_confirmation(fields, filled)}"
    )
    if is_media:
        user = f"[The teacher just sent a {kind}]\n\n{user}"

    try:
        result = await complete_json(
            system,
            user,
            SCHEMA,
            schema_name="followup",
            model=model or MODEL_ASK,
        )
    except Exception:
        return f"{FOLLOWUP_EN}\n{FOLLOWUP_KM}"

    text = _join(result)
    # 両方 null = もう聞くことがない
    if not text or text.strip().upper().startswith("NONE"):
        return None
    return text
