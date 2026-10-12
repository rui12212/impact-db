"""スクールページの「学校全体の変容」「授業研究会コメントの考察」を書く。

  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.school_summary

  # 1校だけ試す
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.school_summary --only "Lab School"

**週1で回す。** マイページの ai_summary と同じ理由（文章が毎日揺れると
信頼を失う）。ただし「記録があった先生の割合」は数字なので毎晩でよい。

⚠️ **先生の名前をLLMに渡さない。** スクールページは
   「個人を評価したり比較したりするためのものではない」。
   プロンプトで禁止するだけでは足りないので、**渡す前に落とす**:

     ① payload に Teacher を入れない（誰の記録かを持たせない）
     ② 本文に出てくる在籍教員の名前を "a teacher" に置き換える

   プロンプトの指示は破られることがあるが、入力に名前が無ければ
   名前は出ない。→ v2-school-page.md §4-2

⚠️ block_id は保存しない。毎回ページを読んで見出しから探す。
   --rebuild でページを作り直しても追従できるようにするため。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from v2_app.batch.ai_summary import _date, _select, _text, paginate, rt, set_callout
from v2_app.scripts.notion_page_create import _title as _page_title
from v2_app.core import page_layout as pl
from v2_app.core.config import (
    DB_DAILY_LEARNING,
    DB_LESSON_STUDY_REFLECTION,
    DB_RESEARCH_QUESTION,
    MODEL_ASK,
)
from v2_app.core.llm import complete_text
from v2_app.core.notion_client import get_notion

log = logging.getLogger("impactdb.v2")

# 比較する窓の大きさ（件数）。
#
# マイページは先生1人なので 5 + 5。**学校は1校14人なので足りない。**
# 1人あたり1〜2件しか入らず、「学校の傾向」ではなく
# 「たまたま最初に書いた数人」の話になる。
# 14人 × 月2〜3件を見込んで 20 + 20 にした。
SCHOOL_WINDOW = 20

# 記録全体がこれだけの日数に渡っていないと対比しない。
# ai_summary と同じ理由（短期間にまとまった記録でAIが時間を誇張する）
MIN_SPAN_DAYS = 30

# プロンプトに入れる1件の長さ
MAX_CHARS_PER_RECORD = 240

# 「記録があった先生の割合」はこれ未満の先生数なら書かない（割合が暴れる）
MIN_TEACHERS_FOR_RATE = 3

# キーワードの行に出す数
TOP_N = 6

# 学校で共通する問いの推移に出す月数
RQ_MONTHS = 6


ANON = "a teacher"

SYSTEM_CHANGE = """You write a short piece for the staff of one primary school
about how reflection across the whole school has been changing.

You are given two sets of records written by the teachers of this school,
with the month each was written: the earliest ones and the most recent ones.
The records are anonymous on purpose. Your job is to name the shift between
the two sets, for the school as a whole.

Rules:
- Write 2 paragraphs. Around 130 words in total.
- Start from what the records used to be about, then what they are about now.
- Name the shift concretely, using the teachers' own words where you can.
- Write about the school as one group. Use "the records", "teachers here".
- **Never name, number, count or describe an individual teacher.** Never
  write "one teacher", "a few teachers", "some teachers wrote". Never
  compare teachers with each other, and never say who is doing more or less.
- Refer to time only as shown in the months. Do NOT guess how long ago.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent anything that is not in the records.
- If the two sets look the same, say what is consistent instead of forcing
  a change.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_CHANGE_SINGLE = """You write a short piece for the staff of one primary
school about what the teachers there have been paying attention to.

You are given recent records written by the teachers of this school. They are
anonymous on purpose. There is not enough history to compare across time yet.

Rules:
- Write 1 paragraph. Around 80 words.
- Name what the records keep returning to, using their own words where you can.
- Write about the school as one group.
- **Never name, number, count or describe an individual teacher.** Never
  compare teachers with each other.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent anything that is not in the records.
- Do NOT mention that history is missing or that you cannot compare.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_COMMENTS = """You write a short piece for the staff of one primary
school about how the comments made at their lesson study sessions have changed.

You are given, for each session month, how many comments fell into each
category, and whether an expert attended that session.

Rules:
- Write 1 paragraph. Around 90 words.
- Say which categories were common early on and which are common now.
- If sessions with an expert are followed by a change, say so plainly, and
  say whether it held in the sessions after.
- **Never name, number or describe an individual teacher.** The comments are
  the school's, not any person's.
- Describe. Do NOT praise, grade, or advise.
- Do NOT invent anything that is not in the data.
- Write in plain English. No headings, no bullet points.
"""

SYSTEM_KM = """You translate a short piece written for Cambodian school staff
into Khmer.

Rules:
- Keep the meaning exactly. Do not add or remove anything.
- Write natural Khmer that a primary school teacher reads easily.
- Keep the same paragraph breaks.
- Output only the Khmer text.
"""


# --------------------------------------------------------------- 名前を落とす

def _name_pattern(names: List[str]) -> Optional[re.Pattern]:
    """在籍教員の名前にあたる正規表現。短すぎる名前は使わない。

    ⚠️ 2文字以下の名前を置き換えると本文を壊す（クメール語は
    単語の区切りが無く、普通の語に当たってしまう）。
    """
    usable = sorted(
        {n.strip() for n in names if len(n.strip()) >= 3},
        key=len,
        reverse=True,   # 長い名前から当てる。部分一致で切れないように
    )
    if not usable:
        return None
    return re.compile("|".join(re.escape(n) for n in usable))


def strip_names(text: str, pattern: Optional[re.Pattern]) -> str:
    """本文から在籍教員の名前を落とす。

    **名簿にある名前しか消せない。** 先生が名簿外の人名を書いていれば
    残る。それでも、スクールページが名前付きで個人を比較する事故は
    これで止まる（→ v2-school-page.md §4-2）。
    """
    if not pattern or not text:
        return text
    return pattern.sub(ANON, text)


# ------------------------------------------------------------------ 集めて切る

async def school_records(school_id: str, db_id: str) -> List[dict]:
    """その学校の記録を日付の古い順に全部。

    ⚠️ 絞るのは School。Teacher ではない。レコードは書き込み時点の
    学校を持っているので、先生が転校しても過去のデータは
    元の学校に残る（→ db-policy §6-1）
    """
    return await paginate(
        db_id,
        filter={"property": "School", "relation": {"contains": school_id}},
        sorts=[{"property": "Date", "direction": "ascending"}],
    )


def split_school(rows: List[dict]) -> Tuple[List[dict], List[dict]]:
    """古い SCHOOL_WINDOW 件と新しい SCHOOL_WINDOW 件に分ける。

    対比できなければ (空, 直近) を返す。呼び出し側が
    SYSTEM_CHANGE_SINGLE に切り替える。

    ⚠️ 期間の幅は「古い窓の先頭 → 新しい窓の末尾」で測る。
    「古い窓の末尾 → 新しい窓の先頭」だと、ちょうど2倍の件数しか
    無いときに窓が隣り合い、連続する記録の差になってしまう
    （ai_summary で踏んだ）
    """
    dated = [r for r in rows if _date(r)]
    if len(dated) < SCHOOL_WINDOW * 2:
        return [], dated[-SCHOOL_WINDOW:]

    early = dated[:SCHOOL_WINDOW]
    recent = dated[-SCHOOL_WINDOW:]

    span_from = date.fromisoformat(_date(early[0])[:10])
    span_to = date.fromisoformat(_date(recent[-1])[:10])
    if (span_to - span_from).days < MIN_SPAN_DAYS:
        return [], dated[-SCHOOL_WINDOW:]

    return early, recent


# -------------------------------------------------------------- プロンプト

def format_records(
    rows: List[dict], note_prop: str, pattern: Optional[re.Pattern]
) -> str:
    """記録をプロンプトの形にする。**誰が書いたかは入れない。**"""
    lines = []
    for row in rows:
        note = _text(row, note_prop).strip().replace("\n", " ")
        if not note:
            continue
        note = strip_names(note, pattern)[:MAX_CHARS_PER_RECORD]
        lines.append(f"- {_date(row)[:7]}  {note}")
    return "\n".join(lines) or "(none)"


def build_change_prompt(
    early: List[dict], recent: List[dict], pattern: Optional[re.Pattern]
) -> str:
    if early:
        return (
            "[Earlier records across the school]\n"
            f"{format_records(early, 'Note', pattern)}\n\n"
            "[Recent records across the school]\n"
            f"{format_records(recent, 'Note', pattern)}"
        )
    return (
        "[Recent records across the school]\n"
        f"{format_records(recent, 'Note', pattern)}"
    )


def sessions_by_month(
    comments: List[dict], expert_months: Dict[str, bool]
) -> str:
    """月ごとのカテゴリー分布と、専門家が来たかどうか。"""
    months: Dict[str, Counter] = {}
    for row in comments:
        month = _date(row)[:7]
        label = _select(row, "Category")
        if not month or not label:
            continue
        months.setdefault(month, Counter())[label] += 1

    if not months:
        return "(none)"

    lines = []
    for month in sorted(months):
        dist = ", ".join(f"{k} x{v}" for k, v in months[month].most_common())
        mark = "  [expert attended]" if expert_months.get(month) else ""
        lines.append(f"- {month}  {dist}{mark}")
    return "\n".join(lines)


# ------------------------------------------------------------------ 生成

async def _en_km(system: str, user: str) -> Tuple[str, str]:
    """英語を作って、それをクメール語に訳す。失敗したら空文字。"""
    try:
        english = await complete_text(system, user, model=MODEL_ASK)
    except Exception:
        log.exception("英語の生成に失敗")
        return "", ""

    if not english:
        return "", ""

    try:
        khmer = await complete_text(SYSTEM_KM, english, model=MODEL_ASK)
    except Exception:
        log.exception("クメール語への翻訳に失敗")
        khmer = ""

    return english, khmer


# ---------------------------------------------------------------- 数字と言葉

def _keywords(page: dict) -> List[str]:
    items = page.get("properties", {}).get("Keywords", {}).get("multi_select", [])
    return [i["name"] for i in items if i.get("name")]


def keyword_runs(rows: List[dict]) -> List[dict]:
    """キーワードの行。頻度で太さと色を変える（マイページと同じ見た目）。"""
    counts: Counter = Counter()
    for row in rows:
        counts.update(_keywords(row))

    if not counts:
        return [rt(pl.PLACEHOLDER_EN, color="gray", italic=True)]

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


def rate_runs(recorded: int, total: int) -> List[dict]:
    """記録があった先生の割合。

    ⚠️ **Notionのチャートでは出せない**（件数は数えられるが
    件数÷件数ができない）。ここだけバッチが文字で書く。

    これは Record Rate（A-2・分母が未決）とは別物。
    こちらの分母は在籍教員数なので、いま計算できる。
    """
    if total < MIN_TEACHERS_FOR_RATE:
        return [rt(f"{recorded} of {total} teachers recorded this month", color="gray")]

    percent = round(recorded * 100 / total)
    return [
        rt(f"{percent}%", bold=True),
        rt(f"  of teachers recorded this month  ({recorded} of {total})"),
    ]


async def recorded_this_month(school_id: str) -> int:
    """今月1件以上書いた先生の数。"""
    today = date.today()
    first = today.replace(day=1).isoformat()
    rows = await paginate(
        DB_DAILY_LEARNING,
        filter={
            "and": [
                {"property": "School", "relation": {"contains": school_id}},
                {"property": "Date", "date": {"on_or_after": first}},
            ]
        },
    )
    teachers = set()
    for row in rows:
        for rel in row.get("properties", {}).get("Teacher", {}).get("relation", []):
            teachers.add(rel["id"])
    return len(teachers)


async def rq_months(school_id: str) -> List[Tuple[str, str]]:
    """学校で共通する問いの推移。(月, 問い) を古い順に。

    同じ月に複数の先生が別の問いを立てるので、**その月にいちばん
    多かった問いを1つ出す。** 全部並べると誰の問いかが見えてしまい、
    「個人を比較しない」から外れる。
    """
    rows = await paginate(
        DB_RESEARCH_QUESTION,
        filter={"property": "School", "relation": {"contains": school_id}},
        sorts=[{"property": "Date", "direction": "ascending"}],
    )

    months: Dict[str, Counter] = {}
    for row in rows:
        month = _date(row)[:7]
        # ⚠️ 問いは title 型のプロパティ（名前は "RQ"）。rich_text ではない
        text = _page_title(row, "RQ").strip()
        if not month or not text:
            continue
        months.setdefault(month, Counter())[text] += 1

    out = [
        (month, months[month].most_common(1)[0][0])
        for month in sorted(months)
    ]
    return out[-RQ_MONTHS:]


# -------------------------------------------------------------- 書き込み

async def set_paragraph(block_id: str, runs: List[dict]) -> None:
    await get_notion().blocks.update(
        block_id=block_id, paragraph={"rich_text": runs}
    )


async def set_bullets(page_id: str, blocks: List[dict], items: List[Tuple[str, str]]) -> bool:
    """「学校が問うてきたこと」の箇条書きを入れ替える。

    ⚠️ 件数が変わるので書き換えでは足りない。一度消して入れ直す。
    Notionに一括削除が無いので1つずつ消す。
    """
    ids = pl.find_all_after(blocks, pl.S_SCHOOL_ASKED, "bulleted_list_item")
    if not ids:
        return False

    notion = get_notion()
    rows = items or [("", pl.PLACEHOLDER_EN)]

    # 1つ目を書き換え、残りを消して、足りない分を足す
    first = rows[0]
    await notion.blocks.update(
        block_id=ids[0],
        bulleted_list_item={
            "rich_text": [
                rt(f"{first[0]}   ", color="gray"),
                rt(first[1]),
            ]
        },
    )
    for block_id in ids[1:]:
        await notion.blocks.delete(block_id=block_id)

    if len(rows) > 1:
        await notion.blocks.children.append(
            block_id=page_id,
            after=ids[0],
            children=[
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [rt(f"{month}   ", color="gray"), rt(text)]
                    },
                }
                for month, text in rows[1:]
            ],
        )
    return True


async def update_header(page_id: str, blocks: List[dict], teachers: int) -> None:
    """ヘッダーの先生の人数を書き換える。

    ⚠️ 人数は生成時の値で固定されてしまう。先生が増えても
    `--rebuild` するまで古いままだった（2026-10-13に実データで発覚）。

    ヘッダーは最初の heading_1 より前にあるので find_header で探す。
    """
    ids = pl.find_header(blocks)
    if not ids:
        return

    notion = get_notion()
    await notion.blocks.update(
        block_id=ids[0],
        paragraph={"rich_text": [rt(f"{teachers} teachers", bold=True)]},
    )
    if len(ids) > 1:
        await notion.blocks.update(
            block_id=ids[1],
            paragraph={
                "rich_text": [rt(f"គ្រូបង្រៀន {teachers} នាក់", color="gray")]
            },
        )


async def update_page(page_id: str, school_id: str) -> bool:
    """1校ぶん書き換える。何か書いたら True。"""
    notion = get_notion()
    res = await notion.blocks.children.list(block_id=page_id, page_size=100)
    blocks = res.get("results", [])

    daily = await school_records(school_id, DB_DAILY_LEARNING)
    comments = await school_records(school_id, DB_LESSON_STUDY_REFLECTION)

    # 名前を落とすための名簿。**在籍中に限らない**（転校した先生の
    # 名前も過去の記録に出てくる）
    from v2_app.scripts.notion_page_create import teachers as all_teachers

    roster = await all_teachers()
    here = [t for t in roster if t["school_id"] == school_id]
    pattern = _name_pattern([t["name"] for t in roster])

    wrote = False

    # --- 0. ヘッダー（先生の人数）---
    total = len(here)
    await update_header(page_id, blocks, total)

    # --- 1. 記録があった先生の割合 ---
    if total:
        recorded = await recorded_this_month(school_id)
        target = pl.find_after(blocks, pl.S_NUMBERS, "paragraph")
        if target:
            await set_paragraph(target, rate_runs(recorded, total))
            wrote = True

    # --- 2. 学校全体の変容 ---
    early, recent = split_school(daily)
    if recent:
        system = SYSTEM_CHANGE if early else SYSTEM_CHANGE_SINGLE
        english, khmer = await _en_km(
            system, build_change_prompt(early, recent, pattern)
        )
        callouts = pl.find_all_after(blocks, pl.S_CHANGE, "callout")
        if english and callouts:
            await set_callout(callouts[0], english)
            wrote = True
        if khmer and len(callouts) >= 2:
            await set_callout(callouts[1], khmer)

        # キーワードの行（LLMは使わない。Keywords を数えて並べるだけ）
        words = pl.find_after(blocks, pl.S_CHANGE, "paragraph")
        if words:
            await set_paragraph(words, keyword_runs(recent))

    # --- 3. 学校が問うてきたこと ---
    items = await rq_months(school_id)
    if items and await set_bullets(page_id, blocks, items):
        wrote = True

    # --- 5. 授業研究会コメントの考察 ---
    if comments:
        expert = await expert_months(school_id)
        english, khmer = await _en_km(
            SYSTEM_COMMENTS,
            "[Comment categories by session month]\n"
            + sessions_by_month(comments, expert),
        )
        callouts = pl.find_all_after(blocks, pl.S_COMMENTS, "callout")
        if english and callouts:
            await set_callout(callouts[0], english)
            wrote = True
        if khmer and len(callouts) >= 2:
            await set_callout(callouts[1], khmer)

    return wrote


async def expert_months(school_id: str) -> Dict[str, bool]:
    """専門家が来た月。{YYYY-MM: True}"""
    from v2_app.core.config import DB_LESSON_STUDY

    rows = await paginate(
        DB_LESSON_STUDY,
        filter={"property": "School", "relation": {"contains": school_id}},
    )
    out: Dict[str, bool] = {}
    for row in rows:
        month = _date(row)[:7]
        visit = row.get("properties", {}).get("Expert Visit", {}).get("checkbox")
        if month and visit:
            out[month] = True
    return out


# --------------------------------------------------------------------- main

async def run(only: Optional[str] = None) -> Dict[str, int]:
    from v2_app.scripts.notion_school_page_create import schools

    rows = await schools()
    if only:
        rows = [s for s in rows if s["name"] == only]

    done = skipped = 0
    for school in rows:
        page_id = pl.page_id_from_url(school["schoolpage"])
        if not page_id:
            log.info("スクールページが無い: %s", school["name"])
            skipped += 1
            continue

        if await update_page(page_id, school["school_id"]):
            log.info("書き換えた: %s", school["name"])
            done += 1
        else:
            log.info("書くものが無い: %s", school["name"])
            skipped += 1

    log.info("更新 %d / スキップ %d", done, skipped)
    return {"updated": done, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="この学校名だけ")
    args = parser.parse_args()
    print(asyncio.run(run(args.only)))
