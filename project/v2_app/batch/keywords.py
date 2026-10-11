"""マイページの「キーワード」と「着目点の変化」を書く。

  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.keywords

  # 1人だけ試す
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.keywords --only <telegram_id>

**週1で回す**（→ v2-todo.md A-10）

**キーワード自体にLLMを使わない。** 先生が書いた言葉から AI が抽出した
`Keywords`（multi_select）を数えて並べるだけ。言い換えさせる意味がなく、
毎週同じデータなら同じ表示になる方が信頼される。
分析の文章だけ LLM を使う（英語・クメール語の2回）。

比較する期間は ai_summary と同じ「古い3ヶ月 + 直近3ヶ月」。
→ proposal §6-1
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from v2_app.batch.ai_summary import all_records, split_windows
from v2_app.core import page_layout as pl
from v2_app.core.config import DB_DAILY_LEARNING, MODEL_ASK
from v2_app.core.llm import complete_text
from v2_app.core.notion_client import get_notion

log = logging.getLogger("impactdb.v2")

# キーワードの行に出す数
TOP_N = 6

# Then / Now に出す数
SHIFT_N = 3

# これ未満のキーワード数なら何も書かない（まだ傾向と言えない）
MIN_KEYWORDS = 3


SYSTEM_EN = """You write one short paragraph for a teacher about what they
have been paying attention to in their own teaching.

You are given the words that appear most often in their records, for the
earliest months and for the most recent months.

Rules:
- Write 1 paragraph. Around 60 words.
- Name which words were central before and which are central now.
- Quote the words themselves.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent words that are not in the lists.
- If the lists are similar, say what has stayed consistent.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_EN_SINGLE = """You write one short paragraph for a teacher about what
they have been paying attention to in their own teaching.

You are given the words that appear most often in their recent records.

Rules:
- Write 1 paragraph. Around 50 words.
- Name which words they keep returning to, and quote them.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent words that are not in the list.
- Do NOT mention that history is missing or that you cannot compare.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_KM = """You translate a short paragraph written to a Cambodian teacher
into Khmer.

Rules:
- Keep the meaning exactly. Do not add or remove anything.
- Keep the quoted words as they are, in their original language.
- Write natural Khmer that a primary school teacher reads easily.
- Output only the Khmer text.
"""

# 画面に出すラベル（英語 · クメール語）
L_THEN = "WHEN YOU STARTED  ·  ពេលអ្នកចាប់ផ្តើម"
L_NOW = "NOW  ·  ឥឡូវនេះ"


# ---------------------------------------------------------------- 集計

def _keywords(page: dict) -> List[str]:
    items = page.get("properties", {}).get("Keywords", {}).get("multi_select", [])
    return [i["name"] for i in items if i.get("name")]


def count_keywords(rows: List[dict]) -> Counter:
    counter: Counter = Counter()
    for row in rows:
        counter.update(_keywords(row))
    return counter


# ------------------------------------------------------------ ブロック

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


def keyword_runs(counts: Counter) -> List[dict]:
    """キーワードの行。頻度で太さと色を変える（モックの word-cloud）。

    1位〜2位  太字 + 茶
    3位〜4位  茶
    それ以下  グレー
    """
    runs: List[dict] = []
    for rank, (word, _n) in enumerate(counts.most_common(TOP_N)):
        if rank < 2:
            runs.append(rt(word, bold=True, color="brown"))
        elif rank < 4:
            runs.append(rt(word, color="brown"))
        else:
            runs.append(rt(word, color="gray"))
        runs.append(rt("      "))
    return runs


def shift_runs(early: Counter, recent: Counter) -> List[dict]:
    """Then / Now を1つのCalloutに2行で入れる。"""
    then = "、".join(w for w, _ in early.most_common(SHIFT_N)) or "—"
    now = "、".join(w for w, _ in recent.most_common(SHIFT_N)) or "—"
    return [
        rt(f"{L_THEN}\n", bold=True, color="gray"),
        rt(f"{then}\n\n", color="gray"),
        rt(f"{L_NOW}\n", bold=True, color="brown"),
        rt(now),
    ]


# -------------------------------------------------------------- 生成

def format_counts(counts: Counter, limit: int = 12) -> str:
    if not counts:
        return "(none)"
    return ", ".join(f"{w} x{n}" for w, n in counts.most_common(limit))


async def make_analysis(
    early: Counter, recent: Counter
) -> Tuple[str, str]:
    """(英語, クメール語) の分析文。失敗したら空文字。"""
    if not recent:
        return "", ""

    comparing = bool(early)
    system = SYSTEM_EN if comparing else SYSTEM_EN_SINGLE
    if comparing:
        user = (
            f"[Earliest months]\n{format_counts(early)}\n\n"
            f"[Most recent months]\n{format_counts(recent)}"
        )
    else:
        user = f"[Recent records]\n{format_counts(recent)}"

    try:
        english = await complete_text(system, user, model=MODEL_ASK)
    except Exception:
        log.exception("キーワード分析の生成に失敗")
        return "", ""

    if not english:
        return "", ""

    try:
        khmer = await complete_text(SYSTEM_KM, english, model=MODEL_ASK)
    except Exception:
        log.exception("クメール語への翻訳に失敗")
        khmer = ""

    return english, khmer


# -------------------------------------------------------- 書き込み

async def set_paragraph(block_id: str, runs: List[dict]) -> None:
    await get_notion().blocks.update(
        block_id=block_id, paragraph={"rich_text": runs}
    )


async def set_callout(block_id: str, runs: List[dict]) -> None:
    await get_notion().blocks.update(
        block_id=block_id, callout={"rich_text": runs}
    )


async def update_page(page_id: str, user_id: str) -> bool:
    notion = get_notion()
    res = await notion.blocks.children.list(block_id=page_id, page_size=100)
    blocks = res.get("results", [])

    daily = await all_records(user_id, DB_DAILY_LEARNING)
    early_rows, recent_rows = split_windows(daily)

    early = count_keywords(early_rows)
    recent = count_keywords(recent_rows)

    if len(recent) < MIN_KEYWORDS:
        log.info("キーワードが %d件しかないので書かない", len(recent))
        return False

    wrote = False

    # --- キーワードの行 ---
    line_id = pl.find_after(blocks, pl.H_DAILY, "paragraph")
    if line_id:
        await set_paragraph(line_id, keyword_runs(recent))
        wrote = True

    # --- 着目点の変化（Callout 3つ: Then/Now, 英語, クメール語）---
    callouts = pl.find_all_after(blocks, pl.H_FOCUS, "callout")
    if callouts:
        await set_callout(callouts[0], shift_runs(early, recent))
        wrote = True

    english, khmer = await make_analysis(early, recent)
    if english and len(callouts) >= 2:
        await set_callout(callouts[1], [rt(english)])
    if khmer and len(callouts) >= 3:
        await set_callout(callouts[2], [rt(khmer)])

    return wrote


# --------------------------------------------------------------------- main

async def run(only: Optional[int] = None) -> Dict[str, int]:
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
