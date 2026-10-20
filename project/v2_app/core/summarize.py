from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.config import MODEL_ASK, MODEL_EXTRACT
from v2_app.core.llm import complete_json, complete_text

log = logging.getLogger("impactdb.v2")

# 抽出するキーワードの上限
MAX_KEYWORDS = 5

# 1語の上限。クメール語は単語間に空白が無いので、空白の有無だけでは
# 句を弾けない。文字数で歯止めをかける
MAX_KEYWORD_CHARS = 30


SYSTEM_SUMMARY = """You write a very short heading for a teacher's reflection.

Rules:
- Reply in the SAME language as the input.
- Format: "<subject or activity> / <what it was about>"
- 20 characters or fewer if possible. One line.
- Output ONLY the heading. No quotes, no explanation.
"""

SYSTEM_SUBJECT = """You read a teacher's reflection and name the school
subject it is about.

Rules:
- Answer with the subject only. No sentence, no explanation.
- **Answer in the teacher's own language**, using their own word for it.
  If they wrote in Khmer, answer in Khmer.
- If the teacher did not say which subject, answer null.
- Do NOT guess from the activity. "group work" is not a subject.
"""

SUBJECT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"subject": {"type": ["string", "null"]}},
    "required": ["subject"],
    "additionalProperties": False,
}

# これより長いものは教科名ではない（文で返ってきている）
MAX_SUBJECT_CHARS = 40

# 「言っていない」をLLMが文字列で返してくることがある
NOT_A_SUBJECT = ("null", "none", "n/a", "na", "unknown", "not detected", "-")

# ⚠️ キーワードは**先生が使った単語をそのまま抜く**（2026-10-13決定）。
# LLMに解釈させない。選ぶ基準だけを与える。
#
# 基準は「**先生の着眼点**」= 授業中に先生が何を見ていたか。
#
# 失敗した3つの方向:
#   ① 「名詞句を取れ」だけ → 文を切り刻むだけ
#      ['half of the students', 'denominators', 'drawing diagrams']
#   ② 「学びを名付けろ」   → LLMが作った言葉。先生は言っていない
#      ['procedural misconception', 'teacher pacing']
#   ③ 言い回しのまま抜く   → 記録ごとに違う語になり、ほぼ全部1件になる
#      ['went back to the diagram', 'a good textbook']
#
# **頻度は追わない**（2026-10-13決定）。どういう語が出てくるかを見るためのもの。
# ただし単語1つに絞ることで、結果として繰り返しも出やすくなる。
SYSTEM_KEYWORDS = """You extract keywords from a teacher's reflection on their
own lesson.

**Every keyword must be a SINGLE WORD copied from the reflection, character
for character.** You are selecting, not writing.

What to select: the words that show WHERE THE TEACHER WAS LOOKING during the
lesson. What were they paying attention to?

Rules:
- ONE word each. Never a phrase. Copy it exactly as it appears in the text.
- Pick 5. If the reflection does not contain 5 worth picking, pick fewer.
- Do NOT rephrase, translate, inflect, or join words.
- Skip names of people, numbers, subject names, and grades.
- Skip function words (the, and, is, very, really, today, learned).
- Negative is fine. A struggle or a missed chance is also something they saw.

Example:
  Reflection: "Today, I learned that for better focus, they need to put their
  tables together. Even though it's four members of group, doesn't matter.
  The textbook is really important."
  Keywords: ["focus", "tables", "group", "textbook"]
"""


SYSTEM_SLACK = """You summarize a teacher's reflection for a team channel.

Rules:
- Reply in the SAME language as the input.
- One or two short sentences. Keep the teacher's own wording where you can.
- State what happened and what they plan to try next, if written.
- Do NOT evaluate. Do NOT praise. Do NOT add advice.
"""

KEYWORDS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["keywords"],
    "additionalProperties": False,
}

async def make_summary(
    fields: List[flow.Field],
    filled: Dict[str, Any],
    *,
    model: Optional[str] = None,
) -> str:
    """Notion の Title に入れる短い見出し。

    Title は必須なので、失敗しても必ず何かを返す。
    """
    body = _main_text(fields, filled)
    fallback = (body[:30] or "(untitled)")

    if not body:
        return fallback

    try:
        text = await complete_text(
            SYSTEM_SUMMARY,
            body,
            max_tokens=60,
            temperature=0.3,
            model=model or MODEL_ASK,
        )
    except Exception:
        return fallback

    text = text.strip().strip('"').strip("「」")
    return text[:100] if text else fallback


async def make_keywords(
    text: str,
    *,
    model: Optional[str] = None,
) -> List[str]:
    """Keywords（Multi-select）に入れる語。失敗したら空リスト。"""
    if not text:
        return []

    try:
        result = await complete_json(
            SYSTEM_KEYWORDS,
            text,
            KEYWORDS_SCHEMA,
            schema_name="keywords",
            model=model or MODEL_EXTRACT,
        )
    except Exception:
        return []
    
    words = result.get("keywords") or []
    # ⚠️ プロンプトだけに頼らず、コード側でも落とす。
    # LLMは「単語1つでそのまま抜け」と言っても、言い換えるし句で返す。
    #   1. 本文に文字列として無い      → 先生が言っていない語
    #   2. 空白を含む                  → 句になっている
    #   3. 長すぎる                    → クメール語は単語間に空白が無いので
    #                                     空白だけでは句を弾けない
    haystack = text.lower()
    seen, out, dropped = set(), [], []
    for w in words:
        w = str(w).strip().strip('"\u201c\u201d').strip(".,;:!?()[]")
        if not w or w.lower() in seen:
            continue
        if any(c.isspace() for c in w):
            dropped.append((w, "phrase"))
            continue
        if len(w) > MAX_KEYWORD_CHARS:
            dropped.append((w, "too_long"))
            continue
        if w.lower() not in haystack:
            dropped.append((w, "not_in_text"))
            continue
        seen.add(w.lower())
        out.append(w)
        if len(out) >= MAX_KEYWORDS:
            break
    if dropped:
        log.info("捨てたキーワード: %s", dropped)
    return out

async def make_slack_text(
    teacher_name: str,
    fields: List[flow.Field],
    filled: Dict[str, Any],
    *,
    head: str = "",
    model: Optional[str]=None
) -> Optional[str]:
  """Slackに流す1通。先生の名前 + 要約。

  head を渡すと1行目を差し替えられる。授業研究で
  「どの会へのコメントか」を出すため（2026-10-13）。
  """
  body = _main_text(fields, filled)
  if not body:
    return None
  
  try:
    summary = await complete_text(
        SYSTEM_SLACK,
        body,
        max_tokens=300,
        temperature=0.3,
        model=model or MODEL_ASK,
    )
  except Exception:
    return None

  if not summary:
    return None
  
  return f"{head or f'{teacher_name} has put the record!'}\n{summary}"

def _main_text(fields: List[flow.Field], filled:Dict[str,Any]) -> str:
    for f in flow.asked_fields(fields):
        if f.get("required") and filled.get(f["key"]):
            return str(filled[f["key"]])
    
    parts = [
        str(filled[f["key"]]) for f in flow.asked_fields(fields) if filled.get(f["key"])
    ]

    return "\n".join(parts)


async def pick_subject(text: str, *, model: Optional[str] = None) -> str:
    """Daily Reflection用。足していった Note から教科を1つ抜く。

    対話中は聞かず、保存の直前に1回だけ判定する（2026-10-19決定）。

    ⚠️ **推測させない。** 言っていなければ空を返す。活動の内容から
    教科を当てさせると、先生が言っていないものが入る（キーワード抽出で
    同じ失敗をした → SYSTEM_KEYWORDS のコメント）。

    ⚠️ **先生の言葉のまま返す。** クメール語ならクメール語。
    マイページとスクールページのカードに出るため。

    返りは常に文字列。入れるものが無ければ ""（Notionには書かない）。
    """
    if not text.strip():
        return ""

    try:
        result = await complete_json(
            SYSTEM_SUBJECT,
            text,
            SUBJECT_SCHEMA,
            schema_name="subject",
            model=model or MODEL_EXTRACT,
        )
    except Exception:
        log.exception("教科の抽出に失敗")
        return ""

    subject = (result.get("subject") or "").strip()

    if subject.lower() in NOT_A_SUBJECT:
        return ""
    if len(subject) > MAX_SUBJECT_CHARS:
        log.info("教科が長すぎるので捨てる: %r", subject[:60])
        return ""

    return subject
