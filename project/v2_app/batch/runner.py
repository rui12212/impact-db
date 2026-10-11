"""バッチの入口。cron から叩く。

  # 毎晩（件数の集計 + 今月の問いの反映）
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.runner daily

  # 週1（AIが書く文章）
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.runner weekly

  # 1つだけ動かす
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.runner weekly --job ai_summary

**毎日と週1に分ける理由**: AIの文章を毎日作り直すと、1日の記録は1〜2件なので
変化が出ないのに文章が揺れる。先生が「昨日と違うことが書いてある」と感じると
信頼を失う。→ v2-todo.md A-10

**1人の失敗で全員を止めない。** 30人のうち1人のデータが変な形をしていても、
残り29人のマイページは更新される。先生から見れば「自分のページが
更新されない」のは致命的で、原因が他人のデータだとは分からない。

終了コード: 1つでも失敗があれば 1。cron が気づけるようにするため。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from v2_app.batch import ai_summary, keywords, monthly_stats
from v2_app.core import page_layout as pl

log = logging.getLogger("impactdb.v2")

# 先生1人を処理する関数の形。(page_id, user_id) -> 何か書いたか
PageJob = Callable[[str, str], Awaitable[bool]]


class Result:
    """1つのジョブの結果。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = 0
        self.skipped = 0
        self.failed = 0
        self.seconds = 0.0
        self.error: Optional[str] = None

    @property
    def bad(self) -> bool:
        return self.failed > 0 or self.error is not None

    def line(self) -> str:
        if self.error:
            return f"  [NG] {self.name:14} ジョブ全体が失敗: {self.error}"
        mark = "NG" if self.failed else "OK"
        return (
            f"  [{mark}] {self.name:14} "
            f"成功{self.ok} / スキップ{self.skipped} / 失敗{self.failed}  "
            f"({self.seconds:.1f}秒)"
        )


async def _for_each_teacher(name: str, job: PageJob) -> Result:
    """先生ごとに処理する。1人の失敗で止めない。

    マイページがまだ無い先生はスキップする（notion_page_create.py を
    先に回す必要がある）。
    """
    # TODO: teachers() は core/user_repo.py に移す。
    # バッチがスクリプトを import しているのは向きとして不自然
    from v2_app.scripts.notion_page_create import teachers

    result = Result(name)
    start = time.monotonic()

    try:
        rows = await teachers()
    except Exception as e:
        result.error = str(e)[:120]
        result.seconds = time.monotonic() - start
        log.exception("%s: 先生の一覧を取れなかった", name)
        return result

    for teacher in rows:
        page_id = pl.page_id_from_url(teacher["mypage"])
        if not page_id:
            result.skipped += 1
            log.info("%s: マイページが無い %s", name, teacher["name"])
            continue

        try:
            wrote = await job(page_id, teacher["user_id"])
        except Exception:
            result.failed += 1
            # ⚠️ ここで止めない。他の先生の処理を続ける
            log.exception("%s: 失敗 %s", name, teacher["name"])
            continue

        if wrote:
            result.ok += 1
        else:
            result.skipped += 1

    result.seconds = time.monotonic() - start
    return result


async def _whole_job(name: str, run: Callable[[], Awaitable[Any]]) -> Result:
    """先生ごとに分けられないジョブ（monthly_stats）用。"""
    result = Result(name)
    start = time.monotonic()
    try:
        out = await run()
        if isinstance(out, dict):
            result.ok = out.get("created", 0) + out.get("updated", 0)
            result.failed = out.get("failed", 0)
    except Exception as e:
        result.error = str(e)[:120]
        log.exception("%s: 失敗", name)
    result.seconds = time.monotonic() - start
    return result


# ------------------------------------------------------------------ ジョブ

DAILY_JOBS = ("monthly_stats",)
WEEKLY_JOBS = ("ai_summary", "keywords")


async def _run_job(name: str) -> Result:
    if name == "monthly_stats":
        return await _whole_job(name, monthly_stats.run)
    if name == "ai_summary":
        return await _for_each_teacher(name, ai_summary.update_page)
    if name == "keywords":
        return await _for_each_teacher(name, keywords.update_page)
    raise ValueError(f"未知のジョブ: {name}")


async def run_jobs(names: List[str]) -> int:
    """順に動かす。1つが失敗しても次を動かす。"""
    log.info("開始: %s", ", ".join(names))
    results = [await _run_job(name) for name in names]

    print()
    print("=== 結果 ===")
    for result in results:
        print(result.line())

    bad = [r for r in results if r.bad]
    total = sum(r.seconds for r in results)
    print(f"\n合計 {total:.1f}秒  失敗したジョブ: {len(bad)}")

    return 1 if bad else 0


async def daily() -> int:
    return await run_jobs(list(DAILY_JOBS))


async def weekly() -> int:
    return await run_jobs(list(WEEKLY_JOBS))


# --------------------------------------------------------------------- main

async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("schedule", choices=("daily", "weekly", "all"))
    parser.add_argument(
        "--job",
        help="このジョブだけ動かす（monthly_stats / ai_summary / keywords）",
    )
    args = parser.parse_args()

    if args.job:
        return await run_jobs([args.job])

    if args.schedule == "daily":
        return await daily()
    if args.schedule == "weekly":
        return await weekly()
    return await run_jobs(list(DAILY_JOBS) + list(WEEKLY_JOBS))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.exit(asyncio.run(main()))
