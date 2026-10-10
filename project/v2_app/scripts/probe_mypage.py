"""マイページの模擬を作る。検証用。

  # 作る（モックデータも入れる）
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/probe_mypage.py

  # 消す（ページとモックデータを全部ゴミ箱へ）
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/probe_mypage.py --clean

UIモック（.claude/topics/cambodia-hearing/UI/teacher-mypage.html）に寄せる。

**方針（2026-10-10）**
モックのテキスト中心の部分は、DBビューではなく**ブロックとして書き込む**。
テーブルで出すとモックの見た目から遠くなるため。

  ブロックで書くも          バッチが毎晩書き換える
    今月のリサーチクエスチョン（大きな文字）
    過去の問い（トグル + 箇条書き）
    AIによる学びのサマリー（Callout）
    キーワード（太さを変えた1行）
    着目点の変化（2カラムで Then / Now）
    コメントの読み比べ（2カラムで 昔 / 今）

  DBビューで出すもの        データが増えれば自動で反映される
    タイムライン（ギャラリー）
    授業研究会の一覧（ギャラリー）
    レベルの推移（積み上げ棒グラフ）
    実践例（ギャラリー）

⚠️ 検証専用。Title/Summary/RQ/Name の先頭に [PROBE] を付けているので
   --clean で確実に消せる。

⚠️ Views API は Notion-Version: 2026-03-11 が必須。notion-client 2.5.0 の
   既定は 2022-06-28 なので、ビュー作成だけ httpx で直接叩く。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Dict, List, Optional

import httpx

from v2_app.core.config import (
    DB_DAILY_LEARNING,
    DB_LESSON_STUDY,
    DB_LESSON_STUDY_REFLECTION,
    DB_PRACTICE_EXAMPLE,
    DB_RESEARCH_QUESTION,
    DB_SCHOOL_MEMBER,
    DB_USER,
    NOTION_API_KEY,
)
from v2_app.core.notion_client import create_page, get_notion, query_database

API = "https://api.notion.com/v1"
VERSION = "2026-03-11"
ROOT_PAGE_ID = "3eb2e6dcc84a809db85bebe4505d7df5"
MARK = "[PROBE]"

TEACHER_NAME = "Sophia Chan"


# ------------------------------------------------------------ ブロックの部品

def rt(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    color: str = "default",
    code: bool = False,
) -> dict:
    return {
        "type": "text",
        "text": {"content": text},
        "annotations": {
            "bold": bold,
            "italic": italic,
            "strikethrough": False,
            "underline": False,
            "code": code,
            "color": color,
        },
    }


def block(kind: str, **payload: Any) -> dict:
    return {"object": "block", "type": kind, kind: payload}


def h1(text: str) -> dict:
    return block("heading_1", rich_text=[rt(text)])


def h2(text: str) -> dict:
    return block("heading_2", rich_text=[rt(text)])


def h3(text: str) -> dict:
    return block("heading_3", rich_text=[rt(text)])


def para(*items: dict) -> dict:
    return block("paragraph", rich_text=list(items))


def hint(text: str) -> dict:
    """モックの section-head の小さい補足文。"""
    return para(rt(text, color="gray", italic=True))


def callout(
    items: List[dict], emoji: str, color: str = "gray_background"
) -> dict:
    return block(
        "callout",
        rich_text=items,
        icon={"type": "emoji", "emoji": emoji},
        color=color,
    )


def quote(*items: dict) -> dict:
    return block("quote", rich_text=list(items))


def bullet(text: str, *, color: str = "default") -> dict:
    return block("bulleted_list_item", rich_text=[rt(text, color=color)])


def toggle(text: str, children: List[dict]) -> dict:
    return block("toggle", rich_text=[rt(text)], children=children)


def columns(*cols: List[dict]) -> dict:
    """横並び。モックの shift / quote-row を再現する。"""
    return block(
        "column_list",
        children=[block("column", children=list(c)) for c in cols],
    )


def divider() -> dict:
    return block("divider")


# ---------------------------------------------------------------- API 補助

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }


async def append(page_id: str, blocks: List[dict]) -> None:
    """ページの末尾にブロックを足す。順番に呼べば並び順が保たれる。"""
    await get_notion().blocks.children.append(block_id=page_id, children=blocks)


async def data_source_id(c: httpx.AsyncClient, db_id: str) -> str:
    res = await c.get(f"{API}/databases/{db_id}")
    res.raise_for_status()
    return res.json()["data_sources"][0]["id"]


async def prop_ids(c: httpx.AsyncClient, ds_id: str) -> Dict[str, str]:
    res = await c.get(f"{API}/data_sources/{ds_id}")
    res.raise_for_status()
    return {k: v["id"] for k, v in res.json()["properties"].items()}


async def make_view(
    c: httpx.AsyncClient,
    page_id: str,
    ds_id: str,
    name: str,
    view_type: str,
    *,
    configuration: Optional[dict] = None,
    filter_: Optional[dict] = None,
    sorts: Optional[List[dict]] = None,
) -> bool:
    body: Dict[str, Any] = {
        "data_source_id": ds_id,
        "name": name,
        "type": view_type,
        "create_database": {"parent": {"type": "page_id", "page_id": page_id}},
    }
    if configuration:
        body["configuration"] = configuration
    if filter_:
        body["filter"] = filter_
    if sorts:
        body["sorts"] = sorts

    res = await c.post(f"{API}/views", json=body)
    if res.status_code >= 300:
        print(f"     [NG] {name}  HTTP {res.status_code}")
        print(f"          {res.json().get('message', '')[:160]}")
        return False
    print(f"     [OK] {name}")
    return True


# -------------------------------------------------------------- モックの文章

SCHOOL_LABEL = "Preah Vihear Primary School  /  2026 Term 2"
TEACHER_ROLE = "Grade 3 homeroom  /  9th year"

RQ_CURRENT = (
    "How can I create more moments where students speak "
    "in their own words?"
)
RQ_UPDATED = "Updated 1 Sep  /  reviewed every month"

RQ_PAST = [
    ("Jun", "How can I tell whether students really understand?"),
    ("Jul", "How should I approach students who rarely speak?"),
    ("Aug", "How can everyone take part in group work?"),
]

AI_SUMMARY = [
    "A year ago, your reflections centred on whether the lesson finished on "
    "time. Over the last three months you write more about how to receive the "
    "silence while students are thinking. Your interest has moved from drawing "
    "out answers quickly to protecting the time to think.",
    "Your comments in lesson study have shifted in the same direction: from "
    "the steps of instruction to the facts of student learning. Next month, "
    "try recording how you changed your questioning, and the change will show "
    "more clearly.",
]

# モックの word-cloud。大きい語を bold にして太さの差を表す
KEYWORDS = [
    ("dialogue", 1),
    ("waiting", 1),
    ("their faces", 2),
    ("pair talk", 2),
    ("silence", 3),
    ("own words", 3),
]

FOCUS_THEN = ["pace", "time allocation"]
FOCUS_NOW = ["student dialogue", "the meaning of silence"]

FOCUS_ANALYSIS = (
    "When you started recording last October, words like \"pace\" and \"time\" "
    "were central. In the last three months, words about the students "
    "themselves appear more often, and in September \"dialogue\" appeared more "
    "than in any month since you began."
)

LEVEL_NOTE = (
    "Recent comments centre on specific observations grounded in the facts of "
    "student learning (level 2c). Six months ago they centred on teaching "
    "technique (levels 1 to 2a)."
)

QUOTE_OLD = (
    "Oct last year  /  Math",
    "level 1",
    "\"If you refine your questions a little more, I think students would "
    "think more deeply.\"",
    "A comment about teaching technique",
)
QUOTE_NEW = (
    "Sep this year  /  Math",
    "level 2c",
    "\"Student A listened to a friend's explanation and restated it in her own "
    "words. That moment stayed with me.\"",
    "A comment about the facts of student learning",
)


# -------------------------------------------------------------- モック投入

def _rel(page_id: str) -> dict:
    return {"relation": [{"id": page_id}]}


def _title(text: str) -> dict:
    return {"title": [{"text": {"content": text}}]}


def _text(text: str) -> dict:
    return {"rich_text": [{"text": {"content": text}}]}


async def find_teacher() -> str:
    res = await query_database(DB_USER, page_size=1)
    results = res.get("results", [])
    if not results:
        raise RuntimeError("User DB が空です。先にBotで /start してください")
    return results[0]["id"]


async def school_of_teacher(user_page_id: str) -> str:
    res = await query_database(
        DB_SCHOOL_MEMBER,
        filter={
            "and": [
                {"property": "User", "relation": {"contains": user_page_id}},
                {"property": "End Date", "date": {"is_empty": True}},
            ]
        },
        page_size=1,
    )
    results = res.get("results", [])
    if not results:
        return ""
    rel = results[0]["properties"].get("School", {}).get("relation", [])
    return rel[0]["id"] if rel else ""


async def seed(user_id: str, school_id: str) -> None:
    print("\n2. モックデータを入れる")

    base: Dict[str, Any] = {"Teacher": _rel(user_id)}
    if school_id:
        base["School"] = _rel(school_id)

    # --- Research Question ---
    rqs = [
        ("2026-06-01", RQ_PAST[0][1], False),
        ("2026-07-01", RQ_PAST[1][1], False),
        ("2026-08-01", RQ_PAST[2][1], False),
        ("2026-09-01", RQ_CURRENT, True),
    ]
    for date, text, current in rqs:
        await create_page(
            DB_RESEARCH_QUESTION,
            {
                "RQ": _title(f"{MARK} {text}"),
                "Date": {"date": {"start": date}},
                "Is Current": {"checkbox": current},
                **base,
            },
        )
    print(f"   Research Question {len(rqs)}件")

    # --- Daily Learning ---
    dailies = [
        ("2026-07-06", "Math", "I rushed to the answer today.", ["pace", "time"]),
        ("2026-07-14", "Khmer", "I talked too much and did not wait.", ["waiting", "my own talk"]),
        ("2026-07-22", "Math", "Finished on time but unsure who understood.", ["pace", "understanding"]),
        ("2026-08-04", "Math", "Tried pair talk. Two quiet students spoke.", ["pair talk", "quiet students"]),
        ("2026-08-11", "Science", "Students observed plants and wrote notes.", ["observation", "writing"]),
        ("2026-08-19", "Khmer", "I waited longer after my question today.", ["waiting", "questioning"]),
        ("2026-08-26", "Math", "A student explained in her own words.", ["own words", "explaining"]),
        ("2026-09-02", "Math", "Checked the weekly goal together with students.", ["goal", "dialogue"]),
        ("2026-09-05", "Khmer", "My explanation got too long again. I could have waited.", ["waiting", "my own talk"]),
        ("2026-09-08", "Math", "Took longer pair time. A quiet child explained softly.", ["pair talk", "quiet students", "dialogue"]),
        ("2026-09-15", "Science", "Students argued about why the leaves changed.", ["dialogue", "reasoning"]),
        ("2026-09-22", "Math", "Silence after my question. I let it stay.", ["silence", "waiting"]),
        ("2026-09-29", "Khmer", "Students read to each other and gave feedback.", ["dialogue", "peer feedback"]),
        ("2026-10-02", "Math", "A student said she noticed her own mistake.", ["own words", "noticing"]),
        ("2026-10-08", "Science", "Kids were focused on talking with each other.", ["dialogue", "focus"]),
    ]
    for date, subject, note, keywords in dailies:
        await create_page(
            DB_DAILY_LEARNING,
            {
                "Summary": _title(f"{MARK} {subject} - {note[:22]}"),
                "Note": _text(note),
                "Subject": _text(subject),
                "Keywords": {"multi_select": [{"name": k} for k in keywords]},
                "Date": {"date": {"start": date}},
                **base,
            },
        )
    print(f"   Daily Learning {len(dailies)}件")

    # --- Lesson Study（箱）。モックの ls-card を出すために必要 ---
    boxes = [
        ("2026-10-15", "Math", "3", "Sophia Chan", False, "Own lesson"),
        ("2026-01-20", "Khmer", "4", "Bopha Sok", True, "Joined"),
        ("2026-05-12", "Math", "3", "Sophia Chan", False, "Own lesson"),
        ("2026-09-18", "Math", "3", "Sophia Chan", False, "Own lesson"),
    ]
    box_ids = []
    for date, subject, grade, teacher_name, expert, role in boxes:
        page = await create_page(
            DB_LESSON_STUDY,
            {
                "Name": _title(f"{MARK} {subject} grade {grade} - {role}"),
                "Date": {"date": {"start": date}},
                "Subject": _text(subject),
                "Grade": _text(grade),
                "Teacher Name": _text(teacher_name),
                "Expert Visit": {"checkbox": expert},
                "Expert Talk": _text("Focus on what students actually said." if expert else ""),
                "Is Closed": {"checkbox": False},
                **({"School": _rel(school_id)} if school_id else {}),
            },
        )
        box_ids.append(page["id"])
    print(f"   Lesson Study {len(boxes)}件")

    # --- Lesson Study Reflection: カテゴリーが月ごとに上がる ---
    comments = [
        ("2026-07-03", "fact:Pure Observation", "Three students did not open their notebooks."),
        ("2026-07-10", "fact:Pure Observation", "The teacher asked six questions in ten minutes."),
        ("2026-07-18", "1:Whole Class", "The class was lively overall."),
        ("2026-08-05", "1:Whole Class", "Most students seemed to follow the lesson."),
        ("2026-08-12", "2a:Individual Behaviour", "Student A kept looking at her neighbour's notebook."),
        ("2026-08-20", "2a:Individual Behaviour", "Student B put his hand up but was not called on."),
        ("2026-09-02", "2b:Individual Understanding", "Student C could not separate the remainder from the quotient."),
        ("2026-09-15", "2c:Examining Causes", "Student C's confusion may come from the diagram being unlabelled."),
        ("2026-10-01", "2c:Examining Causes", "The pair talk worked because the question had no single answer."),
        ("2026-10-08", "2d:Connecting to Practice", "I want to try leaving the diagram unlabelled in my own class."),
    ]
    for i, (date, category, comment) in enumerate(comments):
        await create_page(
            DB_LESSON_STUDY_REFLECTION,
            {
                "Summary": _title(f"{MARK} {comment[:30]}"),
                "Comment": _text(comment),
                "Category": {"select": {"name": category}},
                "Date": {"date": {"start": date}},
                "Lesson Study": _rel(box_ids[i % len(box_ids)]),
                **base,
            },
        )
    print(f"   Lesson Study Reflection {len(comments)}件")

    # --- Practice Example ---
    practices = [
        ("2026-09-03", "Math", "Division with remainders", "Students find the remainder by splitting counters."),
        ("2026-09-17", "Khmer", "Ways to read aloud", "Students try three reading styles and compare."),
        ("2026-10-05", "Science", "Observing plants", "Students record the same plant for two weeks."),
    ]
    for date, subject, title, content in practices:
        await create_page(
            DB_PRACTICE_EXAMPLE,
            {
                "Title": _title(f"{MARK} {title}"),
                "Subject Text": _text(subject),
                "Grade": _text("3"),
                "Aim": _text("Let students find the rule themselves."),
                "Content": _text(content),
                "Reflection": _text("Some students needed more time than planned."),
                "Date": {"date": {"start": date}},
                **base,
            },
        )
    print(f"   Practice Example {len(practices)}件")


# ---------------------------------------------------------------- ページ構築

async def build(page_id: str, user_id: str) -> None:
    print("\n3. ページを組み立てる")

    mine = {"property": "Teacher", "relation": {"contains": user_id}}

    async with httpx.AsyncClient(timeout=60, headers=_headers()) as c:
        ds_daily = await data_source_id(c, DB_DAILY_LEARNING)
        ds_lsr = await data_source_id(c, DB_LESSON_STUDY_REFLECTION)
        ds_box = await data_source_id(c, DB_LESSON_STUDY)
        ds_practice = await data_source_id(c, DB_PRACTICE_EXAMPLE)
        p_lsr = await prop_ids(c, ds_lsr)

        # --- 1. ヘッダー ---
        await append(page_id, [
            para(rt(TEACHER_NAME, bold=True), rt(f"   {TEACHER_ROLE}", color="gray")),
            para(rt(SCHOOL_LABEL, color="gray")),
        ])
        print("   1. ヘッダー")

        # --- 2. 今月のリサーチクエスチョン（大きな文字） ---
        await append(page_id, [
            divider(),
            para(rt("RESEARCH QUESTION FOR THIS MONTH", bold=True, color="brown")),
            h2(RQ_CURRENT),
            para(rt(RQ_UPDATED, color="gray", italic=True)),
            toggle(
                "Past questions",
                [bullet(f"{month}   {text}", color="gray") for month, text in RQ_PAST],
            ),
        ])
        print("   2. リサーチクエスチョン（テキスト）")

        # --- 3. AIによる学びのサマリー ---
        await append(page_id, [
            divider(),
            h2("AI summary of your learning"),
            hint("as of 8 Sep  /  generated from your records"),
            callout([rt(AI_SUMMARY[0])], "✨", "blue_background"),
            callout([rt(AI_SUMMARY[1])], "✨", "blue_background"),
            quote(rt("— from your own records", color="gray", italic=True)),
        ])
        print("   3. AIサマリー")

        # --- 4. 日々の振り返り ---
        await append(page_id, [
            divider(),
            h2("Daily reflections"),
            hint("September 2026  /  23 records"),
        ])

        # word cloud を1行で表す（大きい語を bold に）
        cloud: List[dict] = []
        for word, weight in KEYWORDS:
            cloud.append(rt(word, bold=(weight == 1), color="brown" if weight == 1 else "gray"))
            cloud.append(rt("   "))
        await append(page_id, [para(*cloud)])

        # 着目点の変化を2カラムで
        await append(page_id, [
            columns(
                [
                    para(rt("WHEN YOU STARTED", bold=True, color="gray")),
                    *[bullet(w, color="gray") for w in FOCUS_THEN],
                ],
                [
                    para(rt("NOW", bold=True, color="brown")),
                    *[bullet(w) for w in FOCUS_NOW],
                ],
            ),
            callout([rt(FOCUS_ANALYSIS)], "🔍"),
        ])
        print("   4. 日々の振り返り（キーワード・着目点）")

        # --- 5. タイムライン ---
        await append(page_id, [
            divider(),
            h2("Reflection timeline"),
            hint("transcripts, photos and videos"),
        ])
        if not await make_view(
            c, page_id, ds_daily, "Timeline", "gallery",
            filter_=mine,
            sorts=[{"property": "Date", "direction": "descending"}],
        ):
            await make_view(
                c, page_id, ds_daily, "Timeline", "list",
                filter_=mine,
                sorts=[{"property": "Date", "direction": "descending"}],
            )
        print("   5. タイムライン")

        # --- 6. 授業研究会の記録 ---
        await append(page_id, [
            divider(),
            h2("Lesson study records"),
            hint("how your comment levels changed, the sessions, and a comparison"),
        ])
        await make_view(
            c, page_id, ds_lsr, "Comment levels by month", "chart",
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
            filter_=mine,
        )
        await append(page_id, [callout([rt(LEVEL_NOTE)], "📈")])

        await append(page_id, [h3("The sessions")])
        if not await make_view(
            c, page_id, ds_box, "Sessions", "gallery",
            sorts=[{"property": "Date", "direction": "descending"}],
        ):
            await make_view(
                c, page_id, ds_box, "Sessions", "table",
                sorts=[{"property": "Date", "direction": "descending"}],
            )

        # コメントの読み比べを2カラムで
        await append(page_id, [
            h3("Compare your comments"),
            columns(
                [
                    para(rt(QUOTE_OLD[0], bold=True, color="gray"),
                         rt(f"   {QUOTE_OLD[1]}", code=True)),
                    quote(rt(QUOTE_OLD[2])),
                    para(rt(QUOTE_OLD[3], color="gray", italic=True)),
                ],
                [
                    para(rt(QUOTE_NEW[0], bold=True, color="brown"),
                         rt(f"   {QUOTE_NEW[1]}", code=True)),
                    quote(rt(QUOTE_NEW[2])),
                    para(rt(QUOTE_NEW[3], color="gray", italic=True)),
                ],
            ),
        ])
        print("   6. 授業研究会の記録")

        # --- 7. 実践例 ---
        await append(page_id, [
            divider(),
            h2("Practice examples"),
            hint("all 3"),
        ])
        if not await make_view(
            c, page_id, ds_practice, "My practices", "gallery",
            filter_=mine,
            sorts=[{"property": "Date", "direction": "descending"}],
        ):
            await make_view(
                c, page_id, ds_practice, "My practices", "table",
                filter_=mine,
                sorts=[{"property": "Date", "direction": "descending"}],
            )
        print("   7. 実践例")


# ------------------------------------------------------------------ 片付け

TITLE_PROP = {
    DB_DAILY_LEARNING: "Summary",
    DB_LESSON_STUDY_REFLECTION: "Summary",
    DB_RESEARCH_QUESTION: "RQ",
    DB_PRACTICE_EXAMPLE: "Title",
    DB_LESSON_STUDY: "Name",
}


async def clean() -> int:
    notion = get_notion()
    total = 0

    for db_id, title_prop in TITLE_PROP.items():
        res = await query_database(
            db_id,
            filter={"property": title_prop, "title": {"contains": MARK}},
            page_size=100,
        )
        pages = res.get("results", [])
        for page in pages:
            await notion.pages.update(page_id=page["id"], archived=True)
        total += len(pages)
        print(f"  {title_prop:12} {len(pages)}件")

    res = await notion.search(
        query=MARK, filter={"property": "object", "value": "page"}
    )
    for page in res.get("results", []):
        await notion.pages.update(page_id=page["id"], archived=True)
        print(f"  ページ       {page.get('url')}")
        total += 1

    print(f"\n合計 {total}件をゴミ箱に入れました")
    return 0


# --------------------------------------------------------------------- main

async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="作ったものを全部消す")
    args = parser.parse_args()

    if not NOTION_API_KEY:
        print("NOTION_V2_API_KEY が未設定")
        return 1

    if args.clean:
        return await clean()

    print("1. 先生と学校を引く")
    user_id = await find_teacher()
    school_id = await school_of_teacher(user_id)
    print(f"   user   = {user_id}")
    print(f"   school = {school_id or '(所属なし)'}")

    await seed(user_id, school_id)

    notion = get_notion()
    page = await notion.pages.create(
        parent={"type": "page_id", "page_id": ROOT_PAGE_ID},
        icon={"type": "emoji", "emoji": "🌱"},
        properties={"title": _title(f"{MARK} {TEACHER_NAME}")},
    )
    await build(page["id"], user_id)

    print(f"\n完成: {page['url']}")
    print("\n見終わったら消してください:")
    print("  docker compose -f docker/v2.local.yml exec app \\")
    print("    python project/v2_app/scripts/probe_mypage.py --clean")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
