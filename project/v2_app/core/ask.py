from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.config import MODEL_ASK
from v2_app.core.extract import HISTORY_LAST_N, format_history
from v2_app.core.llm import complete_json

# 必須が埋まったあとに掘り下げる上限（暫定。→ TODO A-8）
MAX_FOLLOWUP = 2


SYSTEM_FIELD = """You are helping a teacher record a reflection on their own teaching.

Ask about ONE missing item, as a natural question in conversation.

Rules:
- Write the SAME question twice: once in English, once in Khmer.
- NEVER use Japanese or any other language.
- One short sentence each. No preamble, no explanation.
- Do NOT sound like a form. Ask as a person would.
- Do NOT give advice. Just ask.
"""

SYSTEM_FOLLOWUP = """You are helping a teacher deepen their reflection on their own teaching.

The teacher has already written what happened. Ask ONE question that invites
them to look more closely at what they observed.

Rules:
- Write the SAME question twice: once in English, once in Khmer.
- NEVER use Japanese or any other language.
- One short sentence each.
- Ask about what they SAW, or what they might try next.
- Do NOT give advice. Do NOT evaluate. Do NOT praise.
- Do NOT repeat a question already asked in the conversation.
- If there is genuinely nothing more to ask, set both fields to null.
"""

async def make_question(
    fields: List[flow.Field],
    filled: Dict[str, Any],
    history: List[Dict[str,str]],
    ask_count: int,
    *,
    model: Optional[str] = None
) -> Optional[str]:
  
  field = flow.next_field(fields, filled)
  if field is not None:
    return await _ask_field(field, history, model)

  if ask_count < MAX_FOLLOWUP:
    return await _ask_followup(fields, filled, history, model)

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
    fallback = field["question"]

    user = (
        f"[What to ask about]\n{fallback}\n\n"
        f"[Conversation so far]\n{format_history(history[-HISTORY_LAST_N:])}"
    )

    try:
        result = await complete_json(
            SYSTEM_FIELD,
            user,
            SCHEMA,
            schema_name="question",
            model=model or MODEL_ASK,
        )
    except Exception:
        return fallback
    return _join(result) or fallback

async def _ask_followup(fields: List[flow.Field], filled:Dict[str,Any],history:List[Dict[str,str]], model:Optional[str]) -> Optional[str]:
    user = (
        f"[Conversation so far]\n{format_history(history[-HISTORY_LAST_N:])}\n\n"
        f"[What has been recorded]\n{flow.render_confirmation(fields, filled)}"
    )

    try:
        result = await complete_json(
            SYSTEM_FOLLOWUP,
            user,
            SCHEMA,
            schema_name="followup",
            model=model or MODEL_ASK,
        )
    except Exception:
        return None

    text = _join(result)
    # 両方 null = もう聞くことがない
    if not text or text.strip().upper().startswith("NONE"):
        return None
    return text