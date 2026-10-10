from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.config import MODEL_ASK, MODEL_EXTRACT
from v2_app.core.llm import complete_json, complete_text

# 抽出するキーワードの上限
MAX_KEYWORDS = 5


SYSTEM_SUMMARY = """You write a very short heading for a teacher's reflection.

Rules:
- Reply in the SAME language as the input.
- Format: "<subject or activity> / <what it was about>"
- 20 characters or fewer if possible. One line.
- Output ONLY the heading. No quotes, no explanation.
"""

SYSTEM_KEYWORDS = """You pick the words a teacher focused on in their reflection.

Rules:
- Use the teacher's OWN words. Do NOT translate. Do NOT paraphrase into formal terms.
- Pick nouns or short noun phrases that show WHERE the teacher's attention was.
- Pick at most 5. Fewer is fine. If nothing stands out, return an empty list.
- Do NOT include the subject name (Math, Khmer) or the grade.
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
    seen, out = set(),[]
    for w in words:
        w=str(w).strip()
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >=MAX_KEYWORDS:
            break
    return out

async def make_slack_text(
    teacher_name: str,
    fields: List[flow.Field],
    filled: Dict[str, Any],
    *,
    model: Optional[str]=None
) -> Optional[str]:
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
  
  return f"{teacher_name} has put the record!\n{summary}"

def _main_text(fields: List[flow.Field], filled:Dict[str,Any]) -> str:
    for f in flow.asked_fields(fields):
        if f.get("required") and filled.get(f["key"]):
            return str(filled[f["key"]])
    
    parts = [
        str(filled[f["key"]]) for f in flow.asked_fields(fields) if filled.get(f["key"])
    ]

    return "\n".join(parts)