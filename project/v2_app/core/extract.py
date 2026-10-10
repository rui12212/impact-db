from __future__ import annotations
from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.config import MODEL_EXTRACT
from v2_app.core.llm import build_object_schema, complete_json

# LLMに渡す会話履歴の件数（→ TODO B-2）
# 20往復でプロンプトが4,000トークンに伸びるので上限を置く
HISTORY_LAST_N = 6

SYSTEM = """You extract structured values from a teacher's reflection.

Rules:
- Fill a field ONLY when the teacher clearly stated it. Otherwise use null.
- Do NOT guess. Do NOT infer from general knowledge.
- Keep the teacher's own wording and language. Do NOT translate.
- Keep each value short. For free-text fields, use the teacher's words as-is.
"""


def _describe_fields(fields: List[flow.Field]) -> str:
    """LLMに「このキーは何か」を伝える。キー名だけでは意味が分からない。"""
    lines = []
    for f in flow.asked_fields(fields):
        label = f.get("label") or f["key"]
        hint = f.get("question") or ""
        lines.append(f'- {f["key"]}: {label}' + (f" ({hint})" if hint else ""))
    return "\n".join(lines)


def format_history(history: List[Dict[str, str]]) -> str:
    """会話履歴をプロンプトに入れる形にする。

    ⚠️ ラベルは英語にする。日本語を混ぜるとモデルがそれを真似て
    日本語で返してくる（Botは英語とクメール語のみ）。
    """
    if not history:
        return "(none)"
    role_en = {"user": "Teacher", "assistant": "Bot"}
    return "\n".join(
        f'{role_en.get(h["role"], h["role"])}: {h["content"]}' for h in history
    )


async def extract_values(
    fields: List[flow.Field],
    history: List[Dict[str, str]],
    latest_text: str,
    *,
    last_n: Optional[int] = HISTORY_LAST_N,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """発言から値を抽出する。

    返すのは {key: 値 or None} の辞書。
    そのまま session.update_filled に渡せる（None は無視される）。
    """
    keys = [f["key"] for f in flow.asked_fields(fields)]
    if not keys:
        return {}

    recent = history[-last_n:] if last_n else history

    user = (
        f"[Fields to extract]\n{_describe_fields(fields)}\n\n"
        f"[Conversation so far]\n{format_history(recent)}\n\n"
        f"[Latest message]\n{latest_text}"
    )

    result = await complete_json(
        SYSTEM,
        user,
        build_object_schema(keys),
        schema_name="extracted_values",
        model=model or MODEL_EXTRACT,
    )

    # 空文字は None に寄せる（update_filled が無視できるように）
    # result の例: {"note": "今日は算数で…", "subject": "算数", "grade": None}
    return {k: (v if v else None) for k, v in result.items() if k in keys}
