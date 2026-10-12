"""探究テーマの入口。会話ループは apps/base.py が持つ。

保存の直前に、この先生の既存の Is Current を false にする。
「今取り組んでいるテーマ」は1人1つだけ。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from v2_app.apps import base
from v2_app.apps.research_question.schema import DB_ID, FIELDS
from v2_app.core import session
from v2_app.core.notion_client import query_database, update_page
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

ROUTE = "research_question"


async def _clear_current(teacher_page_id: str) -> int:
    """この先生の既存の Is Current を全部 false にする。返すのは件数。"""
    res = await query_database(
        DB_ID,
        filter={
            "and": [
                {"property": "Teacher", "relation": {"contains": teacher_page_id}},
                {"property": "Is Current", "checkbox": {"equals": True}},
            ]
        },
        page_size=100,
    )
    pages = res.get("results", [])
    for page in pages:
        await update_page(page["id"], {"Is Current": {"checkbox": False}})
    return len(pages)


async def before_save(inc: Incoming, user: Dict[str, Any]) -> None:
    teacher_page_id = user.get("notion_page_id")

    if teacher_page_id:
        try:
            n = await _clear_current(teacher_page_id)
            if n:
                log.info("既存の Is Current を false にした %d件", n)
        except Exception:
            # 失敗しても新しいテーマは保存する。
            # 古いものが true のまま残るが、記録自体は失わない
            log.exception("既存の Is Current の解除に失敗")

    # 新しいテーマを「今取り組んでいる」にする
    session.update_filled(ROUTE, inc.telegram_id, {"is_current": True})


async def after_save(inc: Incoming, user: Dict[str, Any], page_id: str) -> None:
    """保存した直後にマイページの見出しを最新にする。

    先生が問いを登録して、すぐマイページを開いても反映されている状態にする。
    夜のバッチ（batch/research_question.py）も同じ関数を呼ぶので、
    ここが失敗しても翌朝には追いつく。
    """
    from v2_app.batch import research_question
    from v2_app.core import page_layout as pl

    mypage = pl.page_id_from_url(user.get("mypage") or "")
    if not mypage:
        # マイページがまだ作られていない先生。保存自体は成功している
        return
    await research_question.update_page(mypage, user["notion_page_id"])


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    await base.handle(
        inc,
        user,
        route=ROUTE,
        fields=FIELDS,
        db_id=DB_ID,
        before_save=before_save,
        after_save=after_save,
        # 設定するだけなのでLLMを使わない（2026-10-13）。
        # 打った文がそのまま問いになる。抽出も深掘りもしない
        use_llm=False,
    )
