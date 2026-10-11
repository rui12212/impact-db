"""Teacher Monthly Stats を日次で更新する。

  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.monthly_stats

1先生 × 1ヶ月 = 1行。冪等なので何度動かしても同じ結果になる。
設計 → v2-architecture-db-policy.md §11

**当月と前月の2ヶ月分を更新する（2026-10-10決定）。**
当月だけだと、月末の夜から日付が変わるまでに保存された記録が
永久に集計から漏れる。先生が夜に書く運用では実際に起きる。

起点は「在籍中の School Member」。「記録があった先生」ではない。
記録が0件の先生も0件の行を作る必要がある（記録が滞っている人に
気づくのが目的なので、行が無いと見えなくなる）。
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from v2_app.core.config import (
    DB_DAILY_LEARNING,
    DB_LESSON_STUDY_REFLECTION,
    DB_PRACTICE_EXAMPLE,
    DB_SCHOOL_MEMBER,
    DB_TEACHER_MONTHLY_STATS,
    DB_USER,
)
from v2_app.core.notion_client import create_page, query_database, update_page

log = logging.getLogger("impactdb.v2")

# 当月から何ヶ月前まで遡って更新するか
MONTHS_BACK = 1

# 数える対象。(DB, Notionのプロパティ名)
SOURCES = [
    ("Reflection Count", DB_DAILY_LEARNING),
    ("Practice Count", DB_PRACTICE_EXAMPLE),
    ("Comment Count", DB_LESSON_STUDY_REFLECTION),
]


# ------------------------------------------------------------------ 日付

def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def prev_month(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def periods(today: date) -> List[date]:
    """更新する月初の日付。新しい順。"""
    out = [month_start(today)]
    for _ in range(MONTHS_BACK):
        out.append(prev_month(out[-1]))
    return out


# ---------------------------------------------------------------- Notion

async def paginate(db_id: str, **kwargs: Any) -> List[dict]:
    """全ページ取る。Notionは1回100件まで。"""
    rows: List[dict] = []
    cursor: Optional[str] = None
    while True:
        res = await query_database(
            db_id, page_size=100, **({"start_cursor": cursor} if cursor else {}), **kwargs
        )
        rows.extend(res.get("results", []))
        if not res.get("has_more"):
            return rows
        cursor = res.get("next_cursor")


def _title(page: dict, prop: str) -> str:
    items = page.get("properties", {}).get(prop, {}).get("title", [])
    return "".join(i.get("plain_text", "") for i in items)


def _rel_ids(page: dict, prop: str) -> List[str]:
    return [r["id"] for r in page.get("properties", {}).get(prop, {}).get("relation", [])]


# -------------------------------------------------------------- 集める

async def teacher_names() -> Dict[str, str]:
    """User の page id → Teacher Name。"""
    return {p["id"]: _title(p, "Teacher Name") for p in await paginate(DB_USER)}


async def active_members() -> List[Tuple[str, str]]:
    """在籍中の (user_page_id, school_page_id)。

    End Date が空のものが在籍中。1人が複数校に在籍している想定はしない
    （set_school が転校時に前の在籍を閉じる）。
    """
    rows = await paginate(
        DB_SCHOOL_MEMBER,
        filter={"property": "End Date", "date": {"is_empty": True}},
    )
    out = []
    for row in rows:
        users = _rel_ids(row, "User")
        schools = _rel_ids(row, "School")
        if users:
            out.append((users[0], schools[0] if schools else ""))
    return out


async def counts_in_period(db_id: str, start: date, end: date) -> Dict[str, int]:
    """期間内のレコードを先生ごとに数える。

    先生ごとに問い合わせると 30人 × 3DB で90回になる。
    期間で1回取って Python 側で数える。
    """
    rows = await paginate(
        db_id,
        filter={
            "and": [
                {"property": "Date", "date": {"on_or_after": start.isoformat()}},
                {"property": "Date", "date": {"before": end.isoformat()}},
            ]
        },
    )
    counts: Dict[str, int] = {}
    for row in rows:
        for user_id in _rel_ids(row, "Teacher"):
            counts[user_id] = counts.get(user_id, 0) + 1
    return counts


async def find_row(user_id: str, period: date) -> Optional[str]:
    """その先生・その月の行があれば page id。"""
    res = await query_database(
        DB_TEACHER_MONTHLY_STATS,
        filter={
            "and": [
                {"property": "User", "relation": {"contains": user_id}},
                {"property": "Period", "date": {"equals": period.isoformat()}},
            ]
        },
        page_size=1,
    )
    results = res.get("results", [])
    return results[0]["id"] if results else None


# -------------------------------------------------------------- 書き込む

def build_props(
    name: str,
    user_id: str,
    school_id: str,
    period: date,
    counts: Dict[str, int],
) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "Name": {"title": [{"text": {"content": name}}]},
        "User": {"relation": [{"id": user_id}]},
        "Period": {"date": {"start": period.isoformat()}},
    }
    if school_id:
        props["School"] = {"relation": [{"id": school_id}]}
    for prop_name, _ in SOURCES:
        props[prop_name] = {"number": counts.get(prop_name, 0)}
    return props


async def run(today: Optional[date] = None) -> Dict[str, int]:
    """集計する。返すのは件数の内訳。"""
    today = today or date.today()
    names = await teacher_names()
    members = await active_members()

    log.info("在籍中の先生: %d人", len(members))

    created = updated = failed = 0

    for period in periods(today):
        end = next_month(period)
        label = period.strftime("%Y-%m")

        # 期間ごとに3つのDBを1回ずつ取る
        per_source: Dict[str, Dict[str, int]] = {}
        for prop_name, db_id in SOURCES:
            per_source[prop_name] = await counts_in_period(db_id, period, end)

        for user_id, school_id in members:
            counts = {
                prop_name: per_source[prop_name].get(user_id, 0)
                for prop_name, _ in SOURCES
            }
            name = f"{names.get(user_id, 'Unknown')} {label}"
            props = build_props(name, user_id, school_id, period, counts)

            # ⚠️ 1人の失敗で全員を止めない
            try:
                page_id = await find_row(user_id, period)
                if page_id:
                    await update_page(page_id, props)
                    updated += 1
                else:
                    await create_page(DB_TEACHER_MONTHLY_STATS, props)
                    created += 1
            except Exception:
                failed += 1
                log.exception("集計の書き込みに失敗 %s %s", name, label)

        total = sum(sum(c.values()) for c in per_source.values())
        log.info("%s 集計完了 レコード%d件", label, total)

    log.info("新規 %d行 / 更新 %d行 / 失敗 %d行", created, updated, failed)
    return {
        "created": created,
        "updated": updated,
        "failed": failed,
        "teachers": len(members),
    }


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(asyncio.run(run()))
