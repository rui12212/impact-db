from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2_app.core import flow
from v2_app.core.notion_client import create_page, query_database, update_page

EXTERNAL_ID_PROP = "ExternalID"


def make_external_id(update_id: int) -> str:
    """Telegram の update_id から名札を作る。

    webhook が再送されると同じ update_id が届くので、
    これを突き合わせれば2件にならない。
    """
    return f"tg:{update_id}"


def _external_id(fields: List[flow.Field], filled: Dict[str, Any]) -> Optional[str]:
    """ExternalID を持つDBのときだけ値を返す。無ければ None。"""
    for f in fields:
        if f.get("notion_prop") == EXTERNAL_ID_PROP:
            value = filled.get(f["key"])
            return str(value) if value else None
    return None


async def find_by_external_id(db_id: str, external_id: str) -> Optional[str]:
    """同じ ExternalID のページがあれば page id を返す。"""
    res = await query_database(
        db_id,
        filter={"property": EXTERNAL_ID_PROP, "rich_text": {"equals": external_id}},
        page_size=1,
    )
    results = res.get("results", [])
    return results[0]["id"] if results else None


async def save(
    db_id: str,
    fields: List[flow.Field],
    filled: Dict[str, Any],
    *,
    children: Optional[List[dict]] = None,
) -> str:
    """Notion に保存して page id を返す。

    入力中はNotionに触らない。ここで1回だけ書く（Notion APIは3req/秒）。

    ExternalID を持つDB（Lesson Study Reflection）は、同じIDのページが
    既にあれば新規作成ではなく更新する。webhook の再送で2件になるのを防ぐ。
    連打はここでは防げないので Redis のロックで止める（apps/base.py）。
    """
    props = flow.to_notion_props(fields, filled)
    if not props:
        raise ValueError("書き込む内容がありません")

    external_id = _external_id(fields, filled)
    if external_id:
        existing = await find_by_external_id(db_id, external_id)
        if existing:
            await update_page(existing, props)
            return existing

    kwargs: Dict[str, Any] = {}
    if children:
        kwargs["children"] = children

    page = await create_page(db_id, props, **kwargs)
    return page["id"]
