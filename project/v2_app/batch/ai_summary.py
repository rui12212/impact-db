"""マイページの「AIによる学びのサマリー」と「コメントの読み比べ」を書く。

  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.ai_summary

  # 1人だけ試す
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.ai_summary --only <telegram_id>

**週1で回す**（毎日だと1日の記録が1〜2件なので変化が出ないのに文章が揺れる）
→ v2-todo.md A-10

**読ませるのは「古い10件 + 直近10件」だけ。**
知りたいのは変化の方向であって途中の経過ではない。両端が分かれば方向は書ける。
→ proposal §6-1

**英語とクメール語の2つの Callout を書き換える。**
LLMは言語ごとに1回呼ぶ（1回で両方書かせると品質が落ちる）。
→ proposal §6-2

⚠️ block_id は保存しない。毎回ページを読んで見出しから探す。
   --rebuild でページを作り直しても追従できるようにするため。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from v2_app.core import page_layout as pl
from v2_app.core.config import (
    DB_DAILY_LEARNING,
    DB_LESSON_STUDY_REFLECTION,
    MODEL_ASK,
)
from v2_app.core.llm import complete_text
from v2_app.core.notion_client import get_notion

log = logging.getLogger("impactdb.v2")

# 比較する期間の長さ（月）
# 比較する窓の大きさ（件数）。
# 月で切ると記録がまばらな先生で窓が痩せる。件数なら材料が揃う
WINDOW_SIZE = 10

# 記録全体がこれだけの日数に渡っていないと対比しない（60日 = 約2ヶ月）。
# 件数だけで切ると「3週間で24件」の先生が対比され、AIが
# 「1年前のあなたは」と時間を誇張する。
#
# ⚠️ 「早期の末尾 → 直近の先頭」で測ってはいけない。20件ちょうどだと
# 2つの窓が隣り合い、連続する2件の差になってしまう。
# 「早期の先頭 → 直近の末尾」= 記録全体の幅で測る
MIN_SPAN_DAYS = 60

# 1期間あたりプロンプトに入れる記録の上限
MAX_RECORDS_PER_WINDOW = 40


SYSTEM_EN = """You write a short letter to a teacher about how their own
reflection has changed over time.

You are given two sets of their records with the dates they were written:
their earliest records and their most recent ones. Your job is to name the
shift between them.

Rules:
- Write 2 paragraphs. Around 120 words in total.
- Start from what they used to write about, then what they write about now.
- Name the shift concretely, using their own words where you can.
- Refer to time only as shown in the dates. Do NOT guess how long ago it was.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent anything that is not in the records.
- If the two sets look the same, say what is consistent instead of forcing
  a change.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_EN_SINGLE = """You write a short letter to a teacher about what they
have been paying attention to in their own teaching.

You are given their recent records. There is not enough history to compare
across time yet.

Rules:
- Write 1 paragraph. Around 70 words.
- Name what they keep returning to, using their own words where you can.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent anything that is not in the records.
- Do NOT mention that history is missing or that you cannot compare.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_KM = """You translate a letter written to a Cambodian teacher into Khmer.

Rules:
- Keep the meaning exactly. Do not add or remove anything.
- Write natural Khmer that a primary school teacher reads easily.
- Keep the same paragraph breaks.
- Output only the Khmer text.
"""


# ------------------------------------------------------------------ 日付

# ---------------------------------------------------------------- Notion

async def paginate(db_id: str, **kwargs: Any) -> List[dict]:
    from v2_app.core.notion_client import query_database

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


def _text(page: dict, prop: str) -> str:
    items = page.get("properties", {}).get(prop, {}).get("rich_text", [])
    return "".join(i.get("plain_text", "") for i in items)


def _date(page: dict, prop: str = "Date") -> str:
    return (page.get("properties", {}).get(prop, {}).get("date") or {}).get(
        "start", ""
    ) or ""


def _select(page: dict, prop: str) -> str:
    sel = page.get("properties", {}).get(prop, {}).get("select")
    return sel.get("name", "") if sel else ""


async def all_records(user_id: str, db_id: str) -> List[dict]:
    """その先生の記録を日付の古い順に全部。"""
    return await paginate(
        db_id,
        filter={"property": "Teacher", "relation": {"contains": user_id}},
        sorts=[{"property": "Date", "direction": "ascending"}],
    )


def split_windows(rows: List[dict]) -> Tuple[List[dict], List[dict]]:
    """古い WINDOW_SIZE 件と、新しい WINDOW_SIZE 件に分ける。

    **件数で切る**（月ではない）。記録がまばらな先生でも、
    対比する材料が確実に揃うため。

    ただし記録全体が MIN_SPAN_DAYS に渡っていなければ対比しない。
    件数だけで切ると、短期間にまとめて書いた先生が対比され、
    AIが時間の幅を誇張する。

    対比しない場合は (空, 直近) を返す。呼び出し側が
    SYSTEM_EN_SINGLE に切り替える。
    """
    dated = [r for r in rows if _date(r)]
    if len(dated) < WINDOW_SIZE * 2:
        return [], dated[-MAX_RECORDS_PER_WINDOW:]

    early = dated[:WINDOW_SIZE]
    recent = dated[-WINDOW_SIZE:]

    span_from = date.fromisoformat(_date(early[0])[:10])
    span_to = date.fromisoformat(_date(recent[-1])[:10])
    if (span_to - span_from).days < MIN_SPAN_DAYS:
        return [], dated[-MAX_RECORDS_PER_WINDOW:]

    return early, recent


# ------------------------------------------------------------ プロンプト

def format_records(rows: List[dict], note_prop: str) -> str:
    lines = []
    for row in rows:
        note = _text(row, note_prop).strip().replace("\n", " ")
        if note:
            lines.append(f"- {_date(row)[:7]}  {note[:300]}")
    return "\n".join(lines) or "(none)"


def format_levels(rows: List[dict]) -> str:
    """コメントのカテゴリー分布。「昔はレベル1中心、今は2c中心」を出すため。"""
    counts = Counter(_select(r, "Category") for r in rows if _select(r, "Category"))
    if not counts:
        return "(none)"
    return ", ".join(f"{name} x{n}" for name, n in counts.most_common())


def build_user_prompt(
    early_daily: List[dict],
    recent_daily: List[dict],
    early_comments: List[dict],
    recent_comments: List[dict],
) -> str:
    if early_daily or early_comments:
        return (
            "[Earlier records - daily reflections]\n"
            f"{format_records(early_daily, 'Note')}\n\n"
            "[Earlier records - comment levels in lesson study]\n"
            f"{format_levels(early_comments)}\n\n"
            "[Recent records - daily reflections]\n"
            f"{format_records(recent_daily, 'Note')}\n\n"
            "[Recent records - comment levels in lesson study]\n"
            f"{format_levels(recent_comments)}"
        )
    return (
        "[Recent daily reflections]\n"
        f"{format_records(recent_daily, 'Note')}\n\n"
        "[Recent comment levels in lesson study]\n"
        f"{format_levels(recent_comments)}"
    )


# -------------------------------------------------------------- 生成

async def make_summary(
    early_daily: List[dict],
    recent_daily: List[dict],
    early_comments: List[dict],
    recent_comments: List[dict],
) -> Tuple[str, str]:
    """(英語, クメール語) のサマリー。失敗したら空文字。"""
    total = len(recent_daily) + len(recent_comments)
    if total == 0:
        return "", ""

    comparing = bool(early_daily or early_comments)
    system = SYSTEM_EN if comparing else SYSTEM_EN_SINGLE
    user = build_user_prompt(
        early_daily, recent_daily, early_comments, recent_comments
    )

    try:
        english = await complete_text(system, user, model=MODEL_ASK)
    except Exception:
        log.exception("英語サマリーの生成に失敗")
        return "", ""

    if not english:
        return "", ""

    try:
        khmer = await complete_text(SYSTEM_KM, english, model=MODEL_ASK)
    except Exception:
        log.exception("クメール語への翻訳に失敗")
        khmer = ""

    return english, khmer


def pick_comments(rows: List[dict]) -> Tuple[Optional[dict], Optional[dict]]:
    """読み比べに出す2件。最も古いものと最も新しいもの。"""
    dated = [r for r in rows if _date(r) and _text(r, "Comment")]
    if len(dated) < 2:
        return (dated[0] if dated else None), None
    return dated[0], dated[-1]


# -------------------------------------------------------- 書き込み

def rt(text: str, *, bold: bool = False, italic: bool = False,
       color: str = "default", code: bool = False) -> dict:
    return {
        "type": "text",
        "text": {"content": text[:2000]},
        "annotations": {
            "bold": bold, "italic": italic, "strikethrough": False,
            "underline": False, "code": code, "color": color,
        },
    }


async def set_callout(block_id: str, text: str) -> None:
    await get_notion().blocks.update(
        block_id=block_id, callout={"rich_text": [rt(text)]}
    )


async def write_comparison(
    block_id: str, label: str, level: str, comment: str, color: str
) -> None:
    """読み比べのCalloutを1つ書き換える。"""
    await get_notion().blocks.update(
        block_id=block_id,
        callout={
            "rich_text": [
                rt(f"{label}   ", bold=True, color=color),
                rt(f"{level}\n", code=True),
                rt(f"\u201c{comment}\u201d"),
            ]
        },
    )


async def update_page(page_id: str, user_id: str) -> bool:
    notion = get_notion()
    res = await notion.blocks.children.list(block_id=page_id, page_size=100)
    blocks = res.get("results", [])

    daily = await all_records(user_id, DB_DAILY_LEARNING)
    comments = await all_records(user_id, DB_LESSON_STUDY_REFLECTION)

    early_daily, recent_daily = split_windows(daily)
    early_comments, recent_comments = split_windows(comments)

    english, khmer = await make_summary(
        early_daily, recent_daily, early_comments, recent_comments
    )

    wrote = False

    # --- 学びのサマリー（Callout 2つ）---
    callouts = pl.find_all_after(blocks, pl.H_AI_SUMMARY, "callout")
    if english and len(callouts) >= 1:
        await set_callout(callouts[0], english)
        wrote = True
    if khmer and len(callouts) >= 2:
        await set_callout(callouts[1], khmer)

    # --- コメントの読み比べ（2カラムの中のCallout 2つ）---
    old, new = pick_comments(comments)
    if old is not None and new is not None:
        ids = await column_callouts(page_id, blocks)
        if len(ids) >= 2:
            await write_comparison(
                ids[0], _date(old)[:7], _select(old, "Category"),
                _text(old, "Comment"), "gray",
            )
            await write_comparison(
                ids[1], _date(new)[:7], _select(new, "Category"),
                _text(new, "Comment"), "brown",
            )
            wrote = True

    return wrote


async def column_callouts(page_id: str, blocks: List[dict]) -> List[str]:
    """読み比べの2カラムの中にある Callout の id。

    column_list は子を持つので、1段降りて取りに行く必要がある。
    """
    notion = get_notion()
    target = None
    seen = False
    for block in blocks:
        if block.get("type") == "heading_1":
            if seen:
                break
            continue
        if pl.heading_text(block):
            seen = pl.heading_text(block).startswith(pl.H_COMPARE)
            continue
        if seen and block.get("type") == "column_list":
            target = block["id"]
            break

    if not target:
        return []

    out: List[str] = []
    cols = await notion.blocks.children.list(block_id=target, page_size=10)
    for col in cols.get("results", []):
        kids = await notion.blocks.children.list(block_id=col["id"], page_size=10)
        for kid in kids.get("results", []):
            if kid.get("type") == "callout":
                out.append(kid["id"])
                break
    return out


# --------------------------------------------------------------------- main

async def run(only: Optional[int] = None) -> Dict[str, int]:
    # notion_page_create と同じ「在籍中の先生」の取り方を使う
    from v2_app.scripts.notion_page_create import teachers

    rows = await teachers()
    if only is not None:
        rows = [t for t in rows if t["telegram_id"] == only]

    done = skipped = 0
    for teacher in rows:
        page_id = pl.page_id_from_url(teacher["mypage"])
        if not page_id:
            log.info("マイページが無い: %s", teacher["name"])
            skipped += 1
            continue

        if await update_page(page_id, teacher["user_id"]):
            log.info("書き換えた: %s", teacher["name"])
            done += 1
        else:
            log.info("書くものが無い: %s", teacher["name"])
            skipped += 1

    log.info("更新 %d / スキップ %d", done, skipped)
    return {"updated": done, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, help="この telegram_id の先生だけ")
    args = parser.parse_args()
    print(asyncio.run(run(args.only)))
