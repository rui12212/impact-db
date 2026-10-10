from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.config import MODEL_ASK
from v2_app.core.extract import HISTORY_LAST_N, format_history
from v2_app.core.llm import complete_text

# 必須が埋まったあとに掘り下げる上限（暫定。→ TODO A-8）
MAX_FOLLOWUP = 2


SYSTEM_FIELD = """You are helping a teacher record a reflection on their own teaching.

Ask about ONE missing item, as a natural question in conversation.

Rules:
- Reply ONLY in English or Khmer. NEVER in Japanese or any other language.
- Match the language the teacher is writing in. If unclear, use English.
- One or two short sentences. No preamble, no explanation.
- Do NOT sound like a form. Ask as a person would.
- Do NOT give advice. Just ask.
"""

SYSTEM_FOLLOWUP = """You are helping a teacher deepen their reflection on their own teaching.

The teacher has already written what happened. Ask ONE question that invites
them to look more closely at what they observed.

Rules:
- Reply ONLY in English or Khmer. NEVER in Japanese or any other language.
- Match the language the teacher is writing in. If unclear, use English.
- One or two short sentences.
- Ask about what they SAW, or what they might try next.
- Do NOT give advice. Do NOT evaluate. Do NOT praise.
- Do NOT repeat a question already asked in the conversation.
- If there is genuinely nothing more to ask, reply with exactly: NONE
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


async def _ask_field(field: flow.Field, history:List[Dict[str, str]], model:Optional[str]) -> str:
    fallback = field["question"]

    user = (
        f"[What to ask about]\n{fallback}\n\n"
        f"[Conversation so far]\n{format_history(history[-HISTORY_LAST_N:])}"
    )

    try:
        text = await complete_text(
            SYSTEM_FIELD,
            user,
            max_tokens=120,
            temperature=0.3,
            model=model or MODEL_ASK,
        )
    except Exception:
        return fallback
    return text or fallback

async def _ask_followup(fields: List[flow.Field], filled:Dict[str,Any],history:List[Dict[str,str]], model:Optional[str]) -> Optional[str]:
    user = (
        f"[Conversation so far]\n{format_history(history[-HISTORY_LAST_N:])}\n\n"
        f"[What has been recorded]\n{flow.render_confirmation(fields, filled)}"
    )

    try:
        text = await complete_text(
            SYSTEM_FOLLOWUP,
            user,
            max_tokens=120,
            temperature=0.7,
            model=model or MODEL_ASK,
        )
    except Exception:
        return None
    
    if not text or text.strip().upper().startswith("NONE"):
        return None
    return text