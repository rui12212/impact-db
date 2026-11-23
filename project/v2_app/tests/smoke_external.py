"""外部APIを実際に叩く疎通確認。課金・書き込みが発生するので明示実行のみ。

    # 読むだけ（無料・安全）
    docker compose -f docker/v2.local.yml exec app \
        python -m v2_app.tests.smoke_external --read

    # LLMを1回呼ぶ（わずかに課金される）
    docker compose -f docker/v2.local.yml exec app \
        python -m v2_app.tests.smoke_external --llm

    # Notion に実際に1件書いて消す
    docker compose -f docker/v2.local.yml exec app \
        python -m v2_app.tests.smoke_external --write

書き込みは Daily Learning に1件作り、最後に archived=true にする
（Notion API に完全削除は無い。ゴミ箱に入る）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from v2_app.core import extract, flow, summarize
from v2_app.core.config import DB_DAILY_LEARNING, DB_USER, assert_configured
from v2_app.core.notion_client import get_notion, query_database
from v2_app.tests.fixtures import DAILY_FIELDS

SAMPLE = "今日は5年生の算数で分数の足し算をやりました。半分くらいの子が分母を足してしまっていて、図に戻って説明したら伝わった気がします。"


async def check_read() -> None:
    print("[read] Notion: User DB を1件引く …", end=" ", flush=True)
    res = await query_database(DB_USER, page_size=1)
    print(f"OK（{len(res.get('results', []))}件）")

    print("[read] Notion: Daily Learning のプロパティ名を確認 …", end=" ", flush=True)
    db = await get_notion().databases.retrieve(database_id=DB_DAILY_LEARNING)
    actual = set(db["properties"])
    expected = {
        f["notion_prop"] for f in DAILY_FIELDS if f.get("notion_prop")
    } - {"Subject"}  # fixtures は実スキーマと完全一致ではない
    missing = expected - actual
    print("OK" if not missing else f"NG 足りない: {missing}")


async def check_llm() -> None:
    print("[llm] 抽出 …", end=" ", flush=True)
    values = await extract.extract_values(DAILY_FIELDS, [], SAMPLE)
    print("OK")
    for k, v in values.items():
        print(f"       {k} = {v!r}")

    print("[llm] 見出し …", end=" ", flush=True)
    title = await summarize.make_summary(DAILY_FIELDS, values)
    print(f"OK -> {title!r}")

    print("[llm] キーワード …", end=" ", flush=True)
    kws = await summarize.make_keywords(values.get("note") or SAMPLE)
    print(f"OK -> {kws!r}")


async def check_write() -> None:
    filled = {
        "note": "[SMOKE TEST] " + SAMPLE,
        "subject": "算数",
        "summary": "[SMOKE TEST] 分数の指導",
        "keywords": ["smoke-test"],
        "date": date.today().isoformat(),
    }
    props = flow.to_notion_props(DAILY_FIELDS, filled)
    props.pop("Teacher", None)
    props.pop("Image", None)

    print("[write] Daily Learning に1件作る …", end=" ", flush=True)
    page = await get_notion().pages.create(
        parent={"database_id": DB_DAILY_LEARNING}, properties=props
    )
    print("OK")
    print(f"        {page['url']}")

    print("[write] 作ったページをゴミ箱に入れる …", end=" ", flush=True)
    await get_notion().pages.update(page_id=page["id"], archived=True)
    print("OK")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--read", action="store_true", help="Notionを読むだけ")
    parser.add_argument("--llm", action="store_true", help="LLMを呼ぶ（課金あり）")
    parser.add_argument("--write", action="store_true", help="Notionに書いて消す")
    args = parser.parse_args()

    if not (args.read or args.llm or args.write):
        parser.print_help()
        return 2

    assert_configured()

    if args.read:
        await check_read()
    if args.llm:
        await check_llm()
    if args.write:
        await check_write()
    print("\n完了")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
