"""実践例の入口。会話ループは apps/base.py が持つ。

reflection と違うのは、保存の直前に2つ埋めること:
  Subject    subject_text を教科マスタと照合する
  Materials  添付されたメディアの種類からタグを付ける
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from v2_app.apps import base
from v2_app.apps.practice.schema import DB_ID, FIELDS, MATERIAL_BY_KIND
from v2_app.core import session, subject_resolver
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

ROUTE = "practice"


def _materials(filled: Dict[str, Any]) -> List[str]:
    """添付されたメディアから Materials のタグを作る。

    media 項目に中身があるものだけタグを付ける。
    """
    tags = []
    for f in FIELDS:
        if f.get("source") != "media":
            continue
        if filled.get(f["key"]):
            tag = MATERIAL_BY_KIND.get(f.get("media_kind", ""))
            if tag:
                tags.append(tag)
    return tags


async def before_save(inc: Incoming, user: Dict[str, Any]) -> None:
    """保存の直前に呼ばれる。base が呼ぶ。"""
    filled = (session.get_session(ROUTE, inc.telegram_id) or {}).get("filled", {})

    values: Dict[str, Any] = {"materials": _materials(filled)}

    subject_text = filled.get("subject_text")
    if subject_text:
        try:
            page_id = await subject_resolver.resolve(
                subject_text, user.get("school_id") or None
            )
            if page_id:
                values["subject"] = page_id
        except Exception:
            # 照合に失敗しても Subject Text は残るので保存は続ける
            log.exception("教科の照合に失敗 text=%s", subject_text)

    session.update_filled(ROUTE, inc.telegram_id, values)


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    await base.handle(
        inc,
        user,
        route=ROUTE,
        fields=FIELDS,
        db_id=DB_ID,
        before_save=before_save,
    )
