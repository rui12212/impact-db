"""スクールページを作る。1学校に1ページ。

  # 全校ぶん（Schoolpage が空の学校だけ作る。冪等）
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.scripts.notion_school_page_create

  # 作り直す（中身を全部消して組み直す）
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.scripts.notion_school_page_create --rebuild

  # 1校だけ
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.scripts.notion_school_page_create --only "Lab School"

マイページ（notion_page_create.py）と同じ契約で作る。

  文章 → ブロック / カードとチャート → ビュー / テーブルは使わない
  heading_1 がセクションの区切り
  照合は英語の先頭一致（クメール語の訳を差し替えても壊れない）

⚠️ block_id は保存しない。batch/school_summary.py が毎回ページを読んで
   見出しから探す。--rebuild で作り直しても追従できるようにするため。

→ v2-school-page.md
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from v2_app.core import page_layout as pl
from v2_app.core.config import (
    DB_DAILY_LEARNING,
    DB_LESSON_STUDY,
    DB_LESSON_STUDY_REFLECTION,
    DB_PRACTICE_EXAMPLE,
    DB_RESEARCH_QUESTION,
    DB_SCHOOL,
    DB_SCHOOL_MEMBER,
    SCHOOLPAGE_ROOT_ID,
)
from v2_app.core.notion_client import get_notion, update_page

# マイページ側の部品をそのまま使う。見た目を揃えるため
from v2_app.scripts.notion_page_create import (
    append,
    bullet,
    callout,
    clear_children,
    data_source_id,
    divider,
    gallery_card,
    h1,
    h2,
    hint,
    paginate,
    para,
    prop_ids,
    make_view,
    rt,
    _headers,
    _title,
    _url,
)

log = logging.getLogger("impactdb.v2")

# 学校ページだけの文言（page_layout の見出しではない）
#
# ⚠️ 学期は Notion にデータが無いので書かない（→ §10 未決）。
# 「Term in progress」のような仮の文字を出すと、入っていない情報が
# 入っているように見える
def header_runs(teachers: int) -> List[dict]:
    """ヘッダーの2段落。先生の人数だけを出す。

    school_summary.py が毎回ここを書き換える。人数は増減するので、
    作った時の数を置いたままにしない。
    """
    return [
        para(rt(f"{teachers} teachers", bold=True)),
        para(rt(f"គ្រូបង្រៀន {teachers} នាក់", color="gray")),
    ]
PURPOSE_EN = (
    "This page is for seeing what kind of learning is happening across the "
    "school, and for walking alongside teachers as they reflect. "
    "It is not for evaluating or comparing individual teachers."
)
PURPOSE_KM = (
    "ទំព័រនេះគឺសម្រាប់មើលការរៀនសូត្រដែលកើតឡើងនៅទូទាំងសាលា "
    "និងសម្រាប់ដើរជាមួយគ្រូបង្រៀនក្នុងការឆ្លុះបញ្ចាំង។ "
    "វាមិនមែនសម្រាប់វាយតម្លៃ ឬប្រៀបធៀបគ្រូបង្រៀនម្នាក់ៗទេ។"
)

# セクション8の保留。分母（営業日数 / 目標回数）が先方未決定（A-2）
RECORDING_BLOCKED = (
    "This section stays empty until the denominator for Record Rate is "
    "decided. The monthly figures can be recomputed for past months once "
    "it is set."
)


# ------------------------------------------------------------ 学校を集める

async def schools() -> List[Dict[str, Any]]:
    """学校を全部。(page_id, 学校名, Schoolpage のURL)。"""
    rows = await paginate(DB_SCHOOL)
    return [
        {
            "school_id": p["id"],
            "name": _title(p, "School Name") or "Unknown",
            "schoolpage": _url(p, "Schoolpage"),
        }
        for p in rows
    ]


async def member_count(school_id: str) -> int:
    """在籍中の先生の数。End Date が空のものが在籍中。"""
    rows = await paginate(
        DB_SCHOOL_MEMBER,
        filter={
            "and": [
                {"property": "School", "relation": {"contains": school_id}},
                {"property": "End Date", "date": {"is_empty": True}},
            ]
        },
    )
    return len(rows)


# ------------------------------------------------------------------ 組み立て

async def build(page_id: str, school: Dict[str, Any], teachers: int) -> None:
    school_id = school["school_id"]
    here = {"property": "School", "relation": {"contains": school_id}}

    async with httpx.AsyncClient(timeout=60, headers=_headers()) as c:
        ds_daily = await data_source_id(c, DB_DAILY_LEARNING)
        ds_lsr = await data_source_id(c, DB_LESSON_STUDY_REFLECTION)
        ds_box = await data_source_id(c, DB_LESSON_STUDY)
        ds_practice = await data_source_id(c, DB_PRACTICE_EXAMPLE)
        ds_rq = await data_source_id(c, DB_RESEARCH_QUESTION)
        ds_member = await data_source_id(c, DB_SCHOOL_MEMBER)

        p_daily = await prop_ids(c, ds_daily)
        p_lsr = await prop_ids(c, ds_lsr)
        p_box = await prop_ids(c, ds_box)
        p_practice = await prop_ids(c, ds_practice)
        p_rq = await prop_ids(c, ds_rq)
        p_member = await prop_ids(c, ds_member)

        # --- ヘッダー ---
        await append(page_id, [
            *header_runs(teachers),
            callout(f"{PURPOSE_EN}\n\n{PURPOSE_KM}", "💡"),
        ])

        # --- 1. 今月の数字 ---
        #
        # ⚠️ 「記録があった先生の割合」はチャートで出せない。
        # Notionのチャートは件数を数えられるが件数÷件数ができない。
        # ここだけ paragraph にして school_summary.py が書く
        await append(page_id, [
            divider(),
            h1(pl.label(pl.S_NUMBERS)),
            para(rt(pl.PLACEHOLDER_EN, color="gray", italic=True)),
        ])
        await make_view(
            c, page_id, ds_daily, "Daily reflections this month", "chart",
            configuration={
                "type": "chart",
                "chart_type": "number",
                "y_axis": {"aggregator": "count"},
            },
            filter_=here,
            fallback="list",
        )
        await make_view(
            c, page_id, ds_box, "Lesson studies", "chart",
            configuration={
                "type": "chart",
                "chart_type": "number",
                "y_axis": {"aggregator": "count"},
            },
            filter_=here,
            fallback="list",
        )
        await make_view(
            c, page_id, ds_practice, "Practice examples registered", "chart",
            configuration={
                "type": "chart",
                "chart_type": "number",
                "y_axis": {"aggregator": "count"},
            },
            filter_=here,
            fallback="list",
        )

        # --- 2. 学校全体の変容 ---
        #
        # Callout 2つ。school_summary.py が find_all_after でこの順に書く
        #   0: 英語  1: クメール語
        await append(page_id, [
            divider(),
            h1(pl.label(pl.S_CHANGE)),
            para(rt(pl.PLACEHOLDER_EN, color="gray", italic=True)),
            callout(pl.PLACEHOLDER_EN, "🔍"),
            callout(pl.PLACEHOLDER_KM, "🔍"),
        ])

        # --- 3. 探究テーマ ---
        await append(page_id, [
            divider(),
            h1(pl.label(pl.S_RESEARCH)),
            h2(pl.S_SCHOOL_ASKED),
            bullet(pl.PLACEHOLDER_EN, color="gray"),
        ])
        await make_view(
            c, page_id, ds_rq, "Current research questions", "list",
            filter_={
                "and": [
                    here,
                    {"property": "Is Current", "checkbox": {"equals": True}},
                ]
            },
            sorts=[{"property": "Date", "direction": "descending"}],
        )

        # --- 4. よく出てくる言葉 ---
        #
        # ⚠️ ここはバッチで数えない。Notionが Keywords でグループ化して
        # 自分で数える。数えた結果をブロックに書くと二重管理になる
        # ⚠️ ここの段落はバッチが書き換えない。**注記を固定で置く。**
        # プレースホルダを置くと「Being prepared.」が永久に残る
        # （2026-10-13に実データで発覚）。キーワードの行は
        # 「How this school is changing」側にある
        await append(page_id, [
            divider(),
            h1(pl.label(pl.S_WORDS)),
            hint(
                "The chart counts how many records carry each keyword. "
                "It does not rank teachers."
            ),
        ])
        await make_view(
            c, page_id, ds_daily, "Keywords in this school", "chart",
            configuration={
                "type": "chart",
                "chart_type": "bar",
                "x_axis": {
                    "type": "multi_select",
                    "property_id": p_daily["Keywords"],
                    "sort": {"type": "descending"},
                },
                "y_axis": {"aggregator": "count"},
            },
            filter_=here,
            fallback="list",
        )

        # --- 5. 授業研究会コメントの変化 ---
        #
        # ⚠️ 棒ごとにバッジを付けられないので、教科・学年・専門家の有無は
        # 下のギャラリーに持たせる（カードのプロパティ）
        await append(page_id, [
            divider(),
            h1(pl.label(pl.S_COMMENTS)),
        ])
        await make_view(
            c, page_id, ds_lsr, "Comment levels by session", "chart",
            configuration={
                "type": "chart",
                "chart_type": "column",
                "x_axis": {
                    "type": "date",
                    "property_id": p_lsr["Date"],
                    "group_by": "month",
                    "sort": {"type": "ascending"},
                },
                "y_axis": {"aggregator": "count"},
                "stack_by": {
                    "type": "select",
                    "property_id": p_lsr["Category"],
                    "sort": {"type": "ascending"},
                },
            },
            filter_=here,
        )
        await append(page_id, [h2(pl.label(pl.S_SESSIONS_LIST))])
        await make_view(
            c, page_id, ds_box, "The sessions", "gallery",
            configuration=gallery_card(p_box, "Date", "Subject", "Expert Visit"),
            filter_=here,
            sorts=[{"property": "Date", "direction": "descending"}],
        )
        await append(page_id, [
            callout(pl.PLACEHOLDER_EN, "🔁"),
            callout(pl.PLACEHOLDER_KM, "🔁"),
        ])

        # --- 6. 教員一覧 ---
        #
        # ⚠️ カードからマイページへ直接飛べない。Mypage のURLを持って
        # いるのは User で、ロールアップはAPIで作れない。UIで一度だけ
        # 手で足せば1段になる（→ v2-school-page.md §3-2）
        await append(page_id, [divider(), h1(pl.label(pl.S_TEACHERS))])
        await make_view(
            c, page_id, ds_member, "Teachers here", "gallery",
            configuration=gallery_card(p_member, "User", "Start Date"),
            filter_={
                "and": [
                    here,
                    {"property": "End Date", "date": {"is_empty": True}},
                ]
            },
        )

        # --- 7. 実践例 ---
        await append(page_id, [divider(), h1(pl.label(pl.S_PRACTICE))])
        await make_view(
            c, page_id, ds_practice, "Practices in this school", "gallery",
            configuration=gallery_card(p_practice, "Date", "Subject"),
            filter_=here,
            sorts=[{"property": "Date", "direction": "descending"}],
        )

        # --- 8. 教員ごとの記録の状況（保留）---
        await append(page_id, [
            divider(),
            h1(pl.label(pl.S_RECORDING)),
            callout(f"{pl.PLACEHOLDER_EN}\n{pl.PLACEHOLDER_KM}", "⏳"),
            hint(RECORDING_BLOCKED),
        ])


# ---------------------------------------------------------------- 入口

async def ensure(school: Dict[str, Any]) -> Optional[str]:
    """その学校のスクールページが無ければ作る。あれば何もしない。

    返すのは URL。作れなければ None。冪等。
    """
    if not SCHOOLPAGE_ROOT_ID:
        log.warning("NOTION_V2_SCHOOLPAGE_ROOT_ID が未設定。スクールページを作れない")
        return None

    if school["schoolpage"]:
        return school["schoolpage"]

    teachers = await member_count(school["school_id"])
    notion = get_notion()
    page = await notion.pages.create(
        parent={"type": "page_id", "page_id": SCHOOLPAGE_ROOT_ID},
        icon={"type": "emoji", "emoji": "🏫"},
        properties={"title": {"title": [{"text": {"content": school["name"]}}]}},
    )
    await build(page["id"], school, teachers)
    await update_page(school["school_id"], {"Schoolpage": {"url": page["url"]}})
    log.info("スクールページを作った %s %s", school["name"], page["url"])
    return page["url"]


async def run(rebuild: bool, only: Optional[str]) -> Dict[str, Any]:
    rows = await schools()
    if only:
        rows = [s for s in rows if s["name"] == only]
        if not rows:
            log.warning("その名前の学校が無い: %s", only)

    created = rebuilt = skipped = 0

    for school in rows:
        if rebuild and school["schoolpage"]:
            page_id = pl.page_id_from_url(school["schoolpage"])
            if not page_id:
                skipped += 1
                continue
            removed = await clear_children(page_id)
            teachers = await member_count(school["school_id"])
            await build(page_id, school, teachers)
            print(f"  rebuild  {school['name']}  （{removed}ブロック削除）")
            rebuilt += 1
            continue

        if school["schoolpage"]:
            print(f"  skip     {school['name']}")
            skipped += 1
            continue

        url = await ensure(school)
        if url:
            print(f"  created  {school['name']}  {url}")
            created += 1
        else:
            skipped += 1

    print(f"\n新規 {created} / 作り直し {rebuilt} / スキップ {skipped}")
    return {"created": created, "rebuilt": rebuilt, "skipped": skipped}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="中身を作り直す")
    parser.add_argument("--only", help="この学校名だけ")
    args = parser.parse_args()
    await run(args.rebuild, args.only)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    raise SystemExit(asyncio.run(main()))
