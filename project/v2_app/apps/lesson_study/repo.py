"""Lesson Study（箱）を読む。Botは書かない。

箱はアドミン/スタッフがNotionに直接入力する（db-policy §6-3）。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from v2_app.core.config import DB_LESSON_STUDY
from v2_app.core.notion_client import query_database

# 一覧に出す上限（guide §7-3）
MAX_CHOICES = 5


def _title(page: dict, prop: str) -> str:
    items = page.get("properties", {}).get(prop, {}).get("title", [])
    return "".join(i.get("plain_text", "") for i in items)


def _date(page: dict, prop: str) -> str:
    d = page.get("properties", {}).get(prop, {}).get("date")
    return (d or {}).get("start", "") or ""


async def open_lesson_studies(
    school_page_id: Optional[str] = None,
) -> List[Tuple[str, str, str]]:
    """まだ閉じていない授業研究を新しい順に返す。

    返すのは (page_id, Name, Date) のリスト。最大 MAX_CHOICES 件。

    Is Closed のチェックが外れているものだけ。アドミンが
    チェックを入れると一覧から消え、先生が古い会にコメントを
    付けられなくなる。
    """
    conditions = [{"property": "Is Closed", "checkbox": {"equals": False}}]
    if school_page_id:
        conditions.append(
            {"property": "School", "relation": {"contains": school_page_id}}
        )

    res = await query_database(
        DB_LESSON_STUDY,
        filter={"and": conditions},
        sorts=[{"property": "Date", "direction": "descending"}],
        page_size=MAX_CHOICES,
    )
    return [
        (p["id"], _title(p, "Name"), _date(p, "Date"))
        for p in res.get("results", [])
    ]
