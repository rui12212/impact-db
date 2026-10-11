"""マイページの「今月のリサーチクエスチョン」を最新にする。

  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.research_question

**2つの経路から呼ばれる（2026-10-11決定）**

  ① 先生が問いを保存した直後（apps/research_question/handler.py の after_save）
     → 即時反映。先生がマイページを開いたらもう新しい問いが出ている
  ② 毎晩のバッチ（batch/runner.py の DAILY_JOBS）
     → ①が失敗した時の保険。アドミンがNotionで直接直した場合も拾う

**変わっていなければ何もしない。** 過去の問いのトグルを書き換えるには
既存の箇条書きを1件ずつ削除して足し直すことになる（Notionに一括削除が
無い）。問いは月1回しか変わらないので、見出しを比べて同じなら
その場で終わる（問い合わせ2回で終了・30人で約20秒）。

> Redisに問いの件数を持って変化を検知する案もあったが採らなかった。
> 節約できるのは20秒で、代わりに「Redisが消えたら永久に古いまま」という
> 経路が増える。30人規模では割に合わない。→ v2-todo.md A-12
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Dict, List, Optional

from v2_app.core import page_layout as pl
from v2_app.core.notion_client import get_notion

log = logging.getLogger("impactdb.v2")


def rt(text: str, *, color: str = "default") -> dict:
    return {
        "type": "text",
        "text": {"content": text[:2000]},
        "annotations": {
            "bold": False,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": color,
        },
    }


def _heading_text(block: dict) -> str:
    items = block.get("heading_2", {}).get("rich_text", [])
    return "".join(i.get("plain_text", "") for i in items).strip()


async def _replace_toggle_children(toggle_id: str, lines: List[str]) -> None:
    """トグルの中身を入れ替える。

    ⚠️ Notion に一括削除が無いので1件ずつ消す。
    問いが変わった時だけ呼ぶこと。
    """
    notion = get_notion()
    res = await notion.blocks.children.list(block_id=toggle_id, page_size=100)
    for child in res.get("results", []):
        await notion.blocks.delete(block_id=child["id"])

    if not lines:
        lines = [pl.PLACEHOLDER_EN]

    await notion.blocks.children.append(
        block_id=toggle_id,
        children=[
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [rt(line, color="gray")]},
            }
            for line in lines
        ],
    )


async def update_page(page_id: str, user_id: str) -> bool:
    """マイページの問いを最新にする。書き換えたら True。"""
    # teachers() と同じ理由でスクリプトから借りている
    # TODO: current_rq / past_rqs / teachers は core 側に移す
    from v2_app.scripts.notion_page_create import current_rq, past_rqs

    notion = get_notion()
    res = await notion.blocks.children.list(block_id=page_id, page_size=100)
    blocks = res.get("results", [])

    heading_id = pl.find_after(blocks, pl.H_RESEARCH, "heading_2")
    if not heading_id:
        log.info("問いの見出しが見つからない page=%s", page_id)
        return False

    rq = await current_rq(user_id)
    if not rq:
        # 問いを1件も登録していない先生。空文字で上書きすると見出しが
        # 消えるので、仮置きのままにする
        return False

    current = ""
    for block in blocks:
        if block["id"] == heading_id:
            current = _heading_text(block)
            break

    if current == rq:
        return False          # 変わっていない。ここで終わる

    await notion.blocks.update(
        block_id=heading_id, heading_2={"rich_text": [rt(rq)]}
    )

    # 問いが変わったので、過去の一覧も追いつかせる
    toggle_id = pl.find_after(blocks, pl.H_RESEARCH, "toggle")
    if toggle_id:
        past = await past_rqs(user_id)
        await _replace_toggle_children(
            toggle_id, [f"{month}   {text}" for month, text in past]
        )

    log.info("問いを更新: %s", rq[:60])
    return True


async def run(only: Optional[int] = None) -> Dict[str, int]:
    from v2_app.scripts.notion_page_create import teachers

    rows = await teachers()
    if only is not None:
        rows = [t for t in rows if t["telegram_id"] == only]

    done = skipped = 0
    for teacher in rows:
        page_id = pl.page_id_from_url(teacher["mypage"])
        if not page_id:
            skipped += 1
            continue
        if await update_page(page_id, teacher["user_id"]):
            done += 1
        else:
            skipped += 1

    log.info("更新 %d / 変更なし %d", done, skipped)
    return {"updated": done, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, help="この telegram_id の先生だけ")
    args = parser.parse_args()
    print(asyncio.run(run(args.only)))
