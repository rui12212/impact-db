"""Lesson Study（箱）を読む。Botは書かない。

箱はアドミン/スタッフがNotionに直接入力する（db-policy §6-3）。
"""

from __future__ import annotations

from typing import List, Tuple

from v2_app.core import user_repo
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


async def open_lesson_studies() -> List[Tuple[str, str, str, str]]:
    """まだ閉じていない授業研究を新しい順に返す。

    返すのは (page_id, Name, Date, 学校名) のリスト。最大 MAX_CHOICES 件。

    学校名も返す。学校で絞らなくなったので、どの学校の会なのかが
    分からないと先生が選べない（2026-10-13 ユーザー要望）。

    Is Closed のチェックが外れているものだけ。アドミンが
    チェックを入れると一覧から消え、先生が古い会にコメントを
    付けられなくなる。

    ⚠️ **学校で絞らない。** 先生は自分の所属以外の授業研究にも
    参加するため（2026-10-13 ユーザー判断）。絞っていた間は、
    他校で作られた箱が「開催中のものがありません」になっていた。

    代わりに Date の新しい順で MAX_CHOICES 件に切る。全部出すと
    ボタンが並びすぎる。閉じ忘れた古い箱は自然に下に落ちる。
    """
    res = await query_database(
        DB_LESSON_STUDY,
        filter={"property": "Is Closed", "checkbox": {"equals": False}},
        sorts=[{"property": "Date", "direction": "descending"}],
        page_size=MAX_CHOICES,
    )
    rows = res.get("results", [])

    # 学校名は School リレーションの先にある。箱ごとに引くと
    # 5往復になるので、学校DBを1回読んで引き当てる（学校は数十件）
    schools = dict(await user_repo.list_schools()) if rows else {}

    out = []
    for p in rows:
        name = _title(p, "Name")
        # ⚠️ 名前の無い箱は飛ばす。Notionで行だけ作って名前を
        # 入れていないものがあると、ラベルが空のボタンになって
        # Telegram がメッセージ全体を拒否する
        if not name:
            continue
        ids = [r["id"] for r in p["properties"].get("School", {}).get("relation", [])]
        school = schools.get(ids[0], "") if ids else ""
        out.append((p["id"], name, _date(p, "Date"), school))
    return out
