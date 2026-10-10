"""コメントを8分類に当てる。V1の categorizer を流用（2026-10-10決定 案A）。

精度が未検証のため、現地で使われている実績のあるV1の仕組み
（埋め込みの多数決 + LLM補正）をそのまま使う。
→ 精度の見直しは v2-todo.md B-5

⚠️ 既知の制約: 2c+ Questioning Practice は例文が0件なので
   埋め込みの多数決では絶対に選ばれない → v2-todo.md A-5
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger("impactdb.v2")

# confidence がこれ未満なら Category を空にする。
# 誤ったカテゴリーが付くより、空の方がアドミンが気づける
MIN_CONFIDENCE = 0.4


async def to_english(text: str) -> str:
    """英語でないテキストを英訳する。

    categorizer は英語を前提にしている。音声なら STT が
    Translated_En を作っているが、先生が文字で打った場合は無い。

    Gemini の月次上限を食わないよう、ここは OpenAI を使う。
    """
    from core.audio.stt_translate import oai_translate_km_to_en

    try:
        return await asyncio.to_thread(oai_translate_km_to_en, text) or text
    except Exception:
        log.exception("英訳に失敗")
        return text


async def categorize(text: str, *, text_en: str = "") -> Optional[str]:
    """コメント → Notion の Category に入れる選択肢名。

    返すのは "1:Whole Class" の形（categories.category_label）。
    判定できなければ None で、Category は空のまま保存される。

    text_en があればそれを使う。無ければ英訳してから渡す。
    """
    if not (text or text_en):
        return None

    english = text_en or await to_english(text)

    try:
        from impact_app.categorization.categories import category_label
        from impact_app.categorization.categorizer import categorize as _categorize

        # Chroma と langchain は同期なので別スレッドに逃がす。
        # 初回は seed 70件の埋め込みが走るので数秒かかる
        result = await asyncio.to_thread(_categorize, english)
    except Exception:
        log.exception("分類に失敗")
        return None

    name = result.get("category")
    confidence = float(result.get("confidence") or 0)

    if not name:
        return None

    if confidence < MIN_CONFIDENCE:
        log.info("確信度が低いので Category を空にする %s (%.2f)", name, confidence)
        return None

    log.info("分類: %s (%.2f) %s", name, confidence, result.get("rationale", ""))
    return category_label(name)
