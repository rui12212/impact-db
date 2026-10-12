"""先生ごとのマイページを作る。

  # 親ページを初めて作る（1回だけ。出たIDを env に貼る）
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_page_create.py --init-root

  # 新しい先生の分だけ作る（既にある人は触らない）
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_page_create.py

  # 1人だけ試す
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_page_create.py --only <telegram_id>

  # レイアウトを変えたので全員分を作り直す
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_page_create.py --rebuild

**既定では既にページがある先生を触らない（2026-10-11決定・案C）。**
「新しい先生を追加する」が一番よくある操作なので、それが既存ページを
壊さないようにする。先生が自分でメモを書き足している可能性もある。

作ったページのURLは User.Mypage に書き込む。バッチ（keywords.py /
ai_summary.py）がここを見てブロックを書き換える。

UIは [teacher-mypage.html](../../../.claude/topics/cambodia-hearing/UI/teacher-mypage.html) に寄せる。
**テキストはブロック、カードとグラフはビュー。テーブルは使わない。**
→ dev/2026-10-10.md ステップC

⚠️ Views API は Notion-Version: 2026-03-11 が必須。notion-client 2.5.0 の
   既定は 2022-06-28 なので、ビュー作成だけ httpx で直接叩く。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx

from v2_app.core import page_layout as pl
from v2_app.core.config import (
    DB_DAILY_LEARNING,
    DB_LESSON_STUDY_REFLECTION,
    DB_PRACTICE_EXAMPLE,
    DB_RESEARCH_QUESTION,
    DB_SCHOOL_MEMBER,
    DB_USER,
    NOTION_API_KEY,
)
from v2_app.core.notion_client import get_notion, query_database, update_page

log = logging.getLogger("impactdb.v2")

API = "https://api.notion.com/v1"
VERSION = "2026-03-11"

# page_layout の見出しではないもの（バッチの目印にならない文言）
PAST_QUESTIONS = "Past questions  ·  សំណួរកន្លងមក"

# keywords.py が書き換える時も同じラベルを使う
from v2_app.batch.keywords import L_NOW, L_THEN  # noqa: E402


# --------------------------------------------------------------- ブロック

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
        "text": {"content": text[:2000]},
        "annotations": {
            "bold": bold,
            "italic": italic,
            "strikethrough": False,
            "underline": False,
            "code": code,
            "color": color,
        },
    }


def blk(kind: str, **payload: Any) -> dict:
    return {"object": "block", "type": kind, kind: payload}


def h1(text: str) -> dict:
    """セクションの区切り。page_layout.find_after がこれで打ち切る。"""
    return blk("heading_1", rich_text=[rt(text)])


def h2(text: str) -> dict:
    return blk("heading_2", rich_text=[rt(text)])


def h3(text: str) -> dict:
    return blk("heading_3", rich_text=[rt(text)])


def para(*items: dict) -> dict:
    return blk("paragraph", rich_text=list(items))


def hint(text: str) -> dict:
    return para(rt(text, color="gray", italic=True))


def callout(text: str, emoji: str, color: str = "gray_background") -> dict:
    return blk(
        "callout",
        rich_text=[rt(text)],
        icon={"type": "emoji", "emoji": emoji},
        color=color,
    )


def quote(*items: dict) -> dict:
    return blk("quote", rich_text=list(items))


def bullet(text: str, *, color: str = "default") -> dict:
    return blk("bulleted_list_item", rich_text=[rt(text, color=color)])


def toggle(text: str, children: List[dict]) -> dict:
    return blk("toggle", rich_text=[rt(text)], children=children)


def columns(*cols: List[dict]) -> dict:
    return blk(
        "column_list", children=[blk("column", children=list(c)) for c in cols]
    )


def divider() -> dict:
    return blk("divider")


# ------------------------------------------------------------------ API

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }


async def paginate(db_id: str, **kwargs: Any) -> List[dict]:
    rows: List[dict] = []
    cursor: Optional[str] = None
    while True:
        res = await query_database(
            db_id,
            page_size=100,
            **({"start_cursor": cursor} if cursor else {}),
            **kwargs,
        )
        rows.extend(res.get("results", []))
        if not res.get("has_more"):
            return rows
        cursor = res.get("next_cursor")


async def append(page_id: str, blocks: List[dict]) -> None:
    await get_notion().blocks.children.append(block_id=page_id, children=blocks)


async def clear_children(page_id: str) -> int:
    """ページの中身を全部消す。--rebuild のときだけ呼ぶ。

    ⚠️ Notion に一括削除は無い。1件ずつ DELETE する。
    """
    notion = get_notion()
    removed = 0
    while True:
        res = await notion.blocks.children.list(block_id=page_id, page_size=100)
        blocks = res.get("results", [])
        if not blocks:
            return removed
        for block in blocks:
            await notion.blocks.delete(block_id=block["id"])
            removed += 1
        if not res.get("has_more"):
            return removed


async def data_source_id(c: httpx.AsyncClient, db_id: str) -> str:
    res = await c.get(f"{API}/databases/{db_id}")
    res.raise_for_status()
    return res.json()["data_sources"][0]["id"]


async def prop_ids(c: httpx.AsyncClient, ds_id: str) -> Dict[str, str]:
    res = await c.get(f"{API}/data_sources/{ds_id}")
    res.raise_for_status()
    return {k: v["id"] for k, v in res.json()["properties"].items()}


def gallery_card(props: Dict[str, str], *show: str) -> dict:
    """ギャラリーのカードに出すプロパティを決める configuration。

    タイトルの下に日付などを並べられる。1枚のカードを見れば
    「何を・いつ」が分かる（2026-10-13 ユーザー要望）。

    ⚠️ **書かなかったプロパティは visible:false になる。**
    配列は全置き換えなので、タイトル（property_id は "title"）も
    毎回明示しないとカードの見出しが消える。

    ⚠️ キーは `properties`。`visible_properties` や `card_properties`
    でも **200が返るが黙って無視される**（2026-10-13に実測）。
    """
    items = [{"property_id": "title", "visible": True}]
    for name in show:
        pid = props.get(name)
        if pid:
            items.append({"property_id": pid, "visible": True})
        else:
            log.warning("カードに出せない（プロパティが無い）: %s", name)
    return {"type": "gallery", "properties": items}


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
    fallback: str = "table",
) -> None:
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
    if res.status_code < 300:
        return

    log.warning(
        "ビュー作成に失敗 %s (%s): %s",
        name, view_type, res.json().get("message", "")[:140],
    )
    if view_type == fallback:
        return
    body["type"] = fallback
    body.pop("configuration", None)
    res = await c.post(f"{API}/views", json=body)
    if res.status_code >= 300:
        log.warning("フォールバックも失敗 %s", name)


# ------------------------------------------------------------- 先生を集める

def _title(page: dict, prop: str) -> str:
    items = page.get("properties", {}).get(prop, {}).get("title", [])
    return "".join(i.get("plain_text", "") for i in items)


def _text(page: dict, prop: str) -> str:
    items = page.get("properties", {}).get(prop, {}).get("rich_text", [])
    return "".join(i.get("plain_text", "") for i in items)


def _url(page: dict, prop: str) -> str:
    return page.get("properties", {}).get(prop, {}).get("url") or ""


def _number(page: dict, prop: str) -> Optional[float]:
    return page.get("properties", {}).get(prop, {}).get("number")


def _rel_ids(page: dict, prop: str) -> List[str]:
    return [
        r["id"] for r in page.get("properties", {}).get(prop, {}).get("relation", [])
    ]


async def teachers() -> List[Dict[str, Any]]:
    """在籍中の先生。(user page, school page id, 学校名) をまとめて返す。"""
    users = {p["id"]: p for p in await paginate(DB_USER)}

    members = await paginate(
        DB_SCHOOL_MEMBER,
        filter={"property": "End Date", "date": {"is_empty": True}},
    )

    out: List[Dict[str, Any]] = []
    for member in members:
        user_ids = _rel_ids(member, "User")
        if not user_ids or user_ids[0] not in users:
            continue
        user = users[user_ids[0]]
        schools = _rel_ids(member, "School")
        out.append(
            {
                "user_id": user["id"],
                "name": _title(user, "Teacher Name") or "Unknown",
                "telegram_id": _number(user, "Telegram User ID"),
                "mypage": _url(user, "Mypage"),
                "school_id": schools[0] if schools else "",
                "member_name": _title(member, "Name"),
            }
        )
    return out


async def current_rq(user_id: str) -> str:
    res = await query_database(
        DB_RESEARCH_QUESTION,
        filter={
            "and": [
                {"property": "Teacher", "relation": {"contains": user_id}},
                {"property": "Is Current", "checkbox": {"equals": True}},
            ]
        },
        sorts=[{"property": "Date", "direction": "descending"}],
        page_size=1,
    )
    rows = res.get("results", [])
    return _title(rows[0], "RQ") if rows else ""


async def past_rqs(user_id: str, limit: int = 6) -> List[Tuple[str, str]]:
    res = await query_database(
        DB_RESEARCH_QUESTION,
        filter={
            "and": [
                {"property": "Teacher", "relation": {"contains": user_id}},
                {"property": "Is Current", "checkbox": {"equals": False}},
            ]
        },
        sorts=[{"property": "Date", "direction": "descending"}],
        page_size=limit,
    )
    out = []
    for row in res.get("results", []):
        date = (row["properties"].get("Date", {}).get("date") or {}).get("start", "")
        out.append((date[:7] if date else "", _title(row, "RQ")))
    return out


# ------------------------------------------------------------- ページを組む

async def build(page_id: str, teacher: Dict[str, Any], school_name: str) -> None:
    user_id = teacher["user_id"]
    mine = {"property": "Teacher", "relation": {"contains": user_id}}

    rq = await current_rq(user_id)
    past = await past_rqs(user_id)

    async with httpx.AsyncClient(timeout=60, headers=_headers()) as c:
        ds_daily = await data_source_id(c, DB_DAILY_LEARNING)
        ds_lsr = await data_source_id(c, DB_LESSON_STUDY_REFLECTION)
        ds_practice = await data_source_id(c, DB_PRACTICE_EXAMPLE)
        p_lsr = await prop_ids(c, ds_lsr)
        p_daily = await prop_ids(c, ds_daily)

        # --- ヘッダー ---
        header = [para(rt(teacher["name"], bold=True))]
        if school_name:
            header.append(para(rt(school_name, color="gray")))
        await append(page_id, header)

        # --- 今月のリサーチクエスチョン ---
        # ⚠️ heading_2 がバッチの更新対象。問いが変わると夜に書き換わる
        past_children = (
            [bullet(f"{month}   {text}", color="gray") for month, text in past]
            or [bullet(pl.PLACEHOLDER_EN, color="gray")]
        )
        await append(page_id, [
            divider(),
            h1(pl.label(pl.H_RESEARCH)),
            h2(rq or pl.placeholder()),
            toggle(PAST_QUESTIONS, past_children),
        ])

        # --- AIによる学びのサマリー ---
        await append(page_id, [
            divider(),
            h1(pl.label(pl.H_AI_SUMMARY)),
            hint("generated from your records"),
            # Callout 2つ。1つ目が英語、2つ目がクメール語。
            # ai_summary.py が find_all_after でこの順に書き換える
            callout(pl.PLACEHOLDER_EN, "✨", "blue_background"),
            callout(pl.PLACEHOLDER_KM, "✨", "blue_background"),
            quote(rt("— from your own records", color="gray", italic=True)),
        ])

        # --- 日々の振り返り ---
        # ⚠️ 見出しの直後の paragraph がキーワードの行。バッチが書き換える
        await append(page_id, [
            divider(),
            h1(pl.label(pl.H_DAILY)),
            para(rt(pl.PLACEHOLDER_EN, color="gray", italic=True)),
            h2(pl.label(pl.H_FOCUS)),
            # Callout 3つ。keywords.py が find_all_after でこの順に書き換える
            #   0: Then / Now（上位キーワードを並べる。LLMを使わない）
            #   1: 分析（英語）  2: 分析（クメール語）
            callout(f"{L_THEN}\n—\n\n{L_NOW}\n—", "🔁"),
            callout(pl.PLACEHOLDER_EN, "🔍"),
            callout(pl.PLACEHOLDER_KM, "🔍"),
        ])

        # --- タイムライン ---
        await append(page_id, [divider(), h1(pl.label(pl.H_TIMELINE))])
        await make_view(
            c, page_id, ds_daily, "Timeline", "gallery",
            configuration=gallery_card(p_daily, "Date"),
            filter_=mine,
            sorts=[{"property": "Date", "direction": "descending"}],
            fallback="list",
        )

        # --- 授業研究会の記録 ---
        await append(page_id, [divider(), h1(pl.label(pl.H_LESSON_STUDY))])
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

        # ⚠️ ここは授業研究の「箱」ではなく**自分のリフレクション。**
        # 箱（学校単位の会そのもの）を出していたが、先生が見たいのは
        # 自分が書いたコメントの方（2026-10-13 ユーザー判断）
        await append(page_id, [h2(pl.label(pl.H_SESSIONS))])
        await make_view(
            c, page_id, ds_lsr, "My lesson study reflections", "gallery",
            configuration=gallery_card(p_lsr, "Date"),
            filter_=mine,
            sorts=[{"property": "Date", "direction": "descending"}],
        )

        await append(page_id, [
            h2(pl.label(pl.H_COMPARE)),
            columns(
                [callout(pl.placeholder(), "🕰️")],
                [callout(pl.placeholder(), "🌱")],
            ),
        ])

        # --- 実践例 ---
        await append(page_id, [divider(), h1(pl.label(pl.H_PRACTICE))])
        await make_view(
            c, page_id, ds_practice, "My practices", "gallery",
            filter_=mine,
            sorts=[{"property": "Date", "direction": "descending"}],
        )


# ---------------------------------------------------------------- 親ページ

async def init_root() -> int:
    notion = get_notion()
    root = os.getenv("NOTION_V2_ROOT_PAGE_ID")
    if not root:
        print("NOTION_V2_ROOT_PAGE_ID が未設定です")
        return 1

    page = await notion.pages.create(
        parent={"type": "page_id", "page_id": root},
        icon={"type": "emoji", "emoji": "🌱"},
        properties={"title": {"title": [{"text": {"content": "Teacher Mypages"}}]}},
    )
    page_id = page["id"].replace("-", "")
    print(f"作りました: {page['url']}")
    print("\nenv/v2.local.env に貼ってください:")
    print(f"  NOTION_V2_MYPAGE_ROOT_ID={page_id}")
    print("\nそのあと作り直しが必要です:")
    print("  docker compose -f docker/v2.local.yml up -d --force-recreate app")
    return 0


# --------------------------------------------------------------------- main

async def school_names() -> Dict[str, str]:
    from v2_app.core.config import DB_SCHOOL

    return {p["id"]: _title(p, "School Name") for p in await paginate(DB_SCHOOL)}


async def ensure_by_user_id(user_id: str) -> Optional[str]:
    """その先生のマイページが無ければ作る。あれば何もしない。

    返すのは URL（作った / 既にあった）。作れなければ None。

    **所属を選んだ直後に Bot から呼ばれる**（router/menu.py）。
    先生が登録した時点でマイページが存在しないと、見に行く場所が無い。

    冪等。既に Mypage が入っていればNotionに1回も書かない。
    """
    root = os.getenv("NOTION_V2_MYPAGE_ROOT_ID")
    if not root:
        log.warning("NOTION_V2_MYPAGE_ROOT_ID が未設定。マイページを作れない")
        return None

    rows = [t for t in await teachers() if t["user_id"] == user_id]
    if not rows:
        log.info("在籍中の School Member が無い user=%s", user_id)
        return None

    teacher = rows[0]
    if teacher["mypage"]:
        return teacher["mypage"]

    schools = await school_names()
    notion = get_notion()
    page = await notion.pages.create(
        parent={"type": "page_id", "page_id": root},
        icon={"type": "emoji", "emoji": "🌱"},
        properties={"title": {"title": [{"text": {"content": teacher["name"]}}]}},
    )
    await build(page["id"], teacher, schools.get(teacher["school_id"], ""))
    await update_page(user_id, {"Mypage": {"url": page["url"]}})
    log.info("マイページを作った %s %s", teacher["name"], page["url"])
    return page["url"]


async def refresh_header(user_id: str) -> bool:
    """マイページ先頭の「名前」「学校名」とページタイトルを最新にする。

    **設定モードで名前や学校を変えた直後に裏で呼ばれる**
    （router/menu.py ではなく apps/settings/handler.py）。

    ⚠️ ヘッダーはブロックとして書いてあるので、Notionのリレーションの
    ように自動で追従しない。名前を直しても `--rebuild` するまで
    古いままだった（2026-10-13に発覚）。

    変わっていなければ何も書かない。
    """
    rows = [t for t in await teachers() if t["user_id"] == user_id]
    if not rows:
        return False

    teacher = rows[0]
    page_id = pl.page_id_from_url(teacher["mypage"])
    if not page_id:
        return False

    schools = await school_names()
    school = schools.get(teacher["school_id"], "")

    notion = get_notion()
    res = await notion.blocks.children.list(block_id=page_id, page_size=100)
    header = pl.find_header(res.get("results", []))

    if not header:
        log.warning("ヘッダーの段落が見つからない page=%s", page_id)
        return False

    await notion.blocks.update(
        block_id=header[0],
        paragraph={"rich_text": [rt(teacher["name"], bold=True)]},
    )

    if len(header) > 1:
        await notion.blocks.update(
            block_id=header[1],
            paragraph={"rich_text": [rt(school, color="gray")]},
        )
    elif school:
        # 所属を選ばずに作られたページ。学校名の段落がまだ無い。
        # after を付けて名前のすぐ下に入れる（末尾に付くと最下部に落ちる）
        await notion.blocks.children.append(
            block_id=page_id,
            children=[para(rt(school, color="gray"))],
            after=header[0],
        )

    # ページのタイトルも先生の名前。Notionのサイドバーとリンクに出る
    await notion.pages.update(
        page_id=page_id,
        properties={"title": {"title": [{"text": {"content": teacher["name"]}}]}},
    )

    log.info("マイページのヘッダーを更新 %s / %s", teacher["name"], school)
    return True


async def run(rebuild: bool, only: Optional[int]) -> Dict[str, int]:
    root = os.getenv("NOTION_V2_MYPAGE_ROOT_ID")
    if not root:
        print("NOTION_V2_MYPAGE_ROOT_ID が未設定です。")
        print("まず親ページを作ってください:")
        print("  python project/v2_app/scripts/notion_page_create.py --init-root")
        return {"error": 1}

    notion = get_notion()
    schools = await school_names()
    rows = await teachers()

    if only is not None:
        rows = [t for t in rows if t["telegram_id"] == only]
        if not rows:
            print(f"telegram_id={only} の在籍中の先生が見つかりません")
            return {"error": 1}

    created = rebuilt = skipped = 0

    for teacher in rows:
        name = teacher["name"]
        existing = pl.page_id_from_url(teacher["mypage"])

        if existing and not rebuild:
            print(f"  skip     {name}")
            skipped += 1
            continue

        school_name = schools.get(teacher["school_id"], "")

        if existing:
            n = await clear_children(existing)
            await build(existing, teacher, school_name)
            print(f"  rebuild  {name}  （{n}ブロック削除）")
            rebuilt += 1
            continue

        page = await notion.pages.create(
            parent={"type": "page_id", "page_id": root},
            icon={"type": "emoji", "emoji": "🌱"},
            properties={"title": {"title": [{"text": {"content": name}}]}},
        )
        await build(page["id"], teacher, school_name)
        await update_page(teacher["user_id"], {"Mypage": {"url": page["url"]}})
        print(f"  create   {name}  {page['url']}")
        created += 1

    print(f"\n新規 {created} / 作り直し {rebuilt} / スキップ {skipped}")
    return {"created": created, "rebuilt": rebuilt, "skipped": skipped}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-root", action="store_true", help="親ページを作る")
    parser.add_argument("--rebuild", action="store_true", help="既存ページも作り直す")
    parser.add_argument("--only", type=int, help="この telegram_id の先生だけ")
    args = parser.parse_args()

    if not NOTION_API_KEY:
        print("NOTION_V2_API_KEY が未設定")
        return 1

    if args.init_root:
        return await init_root()

    result = await run(args.rebuild, args.only)
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(asyncio.run(main()))
