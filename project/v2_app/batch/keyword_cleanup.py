"""Keywords の未使用の選択肢を消す。

  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.keyword_cleanup --dry-run
  docker compose -f docker/v2.local.yml exec app \
      python -m v2_app.batch.keyword_cleanup

**毎晩回す**（2026-10-13 ユーザー判断）。

溜まるのは毎日なので、週1だと**最大6日間ゴミが見える。**
処理も軽い（読み取り数回 + 消すものが無ければ書き込み0回）。
毎晩なら1回に消す量が小さく、おかしい時に気づきやすい。

なぜ必要か
----------
`Keywords` は multi_select なので、**一度でも使われた値が選択肢として
残り続ける。** 先生が記録するたびに増え、30人なら月3,000語分になる。
重複を除いても1年で数百〜1,000以上になり、ドロップダウンが使えなくなる。

ただし multi_select をやめると、頻度を数える仕組みが全部止まる
（スクールページの棒グラフは**チャートの軸が multi_select 型しか
受け付けない。** マイページのキーワード行と着目点の変化も Keywords を
数えている）。なので **型は変えず、使われていないものだけ消す。**

⚠️ Notion API の挙動（2026-10-10 / 10-13 に実機で確認）
--------------------------------------------------------
1. **`options` はリスト全体の置き換え。** 渡さなかった選択肢は削除される
2. **選択肢の名前は id を渡しても変更できない。** 無視されてエラーも出ない
3. **残すものは `id` ごと渡す。** 名前だけ渡すと別の選択肢として作り直され、
   既にレコードに付いているタグが外れる
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, Dict, List, Set

import httpx

from v2_app.core.config import DB_DAILY_LEARNING, NOTION_API_KEY

log = logging.getLogger("impactdb.v2")

API = "https://api.notion.com/v1"
VERSION = "2026-03-11"

# 対象のプロパティ。他のDBに Keywords を足したらここに増やす
TARGETS = ((DB_DAILY_LEARNING, "Keywords"),)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }


async def _data_source_id(c: httpx.AsyncClient, db_id: str) -> str:
    res = await c.get(f"{API}/databases/{db_id}")
    res.raise_for_status()
    return res.json()["data_sources"][0]["id"]


async def used_names(c: httpx.AsyncClient, ds_id: str, prop: str) -> Set[str]:
    """レコードに実際に付いている値を集める。

    ⚠️ **全レコードを見る。** 1件でも使っていれば残す。
    ページ送りを最後まで辿らないと、古い記録で使われている値を
    消してしまう（タグが外れる）。
    """
    names: Set[str] = set()
    cursor = None
    while True:
        body: Dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        res = await c.post(f"{API}/data_sources/{ds_id}/query", json=body)
        res.raise_for_status()
        data = res.json()

        for page in data.get("results", []):
            items = page.get("properties", {}).get(prop, {}).get("multi_select", [])
            for item in items:
                if item.get("name"):
                    names.add(item["name"])

        if not data.get("has_more"):
            return names
        cursor = data.get("next_cursor")


async def current_options(
    c: httpx.AsyncClient, ds_id: str, prop: str
) -> List[Dict[str, Any]]:
    res = await c.get(f"{API}/data_sources/{ds_id}")
    res.raise_for_status()
    schema = res.json()["properties"].get(prop, {})
    return schema.get("multi_select", {}).get("options", [])


async def prune_one(
    c: httpx.AsyncClient, db_id: str, prop: str, *, dry_run: bool
) -> Dict[str, Any]:
    ds_id = await _data_source_id(c, db_id)
    options = await current_options(c, ds_id, prop)
    if not options:
        return {"before": 0, "removed": 0, "kept": 0, "names": []}

    used = await used_names(c, ds_id, prop)

    # ⚠️ **1件も使われていないなら何もしない。** 安全装置。
    #
    # ここを素通りさせると「全選択肢の削除」になる。無人で毎晩走るので、
    # Notionの障害でクエリが空を返した時に**既存レコードのタグが
    # 全部外れる。** 本当に0件なら消す意味もない（次の記録で作り直される）
    if not used:
        log.info("%s を使っているレコードが無い。何もしない", prop)
        result_empty: Dict[str, Any] = {
            "before": len(options),
            "removed": 0,
            "kept": len(options),
            "names": [],
            "skipped": True,
        }
        return result_empty

    keep = [o for o in options if o.get("name") in used]
    drop = [o["name"] for o in options if o.get("name") not in used]

    result: Dict[str, Any] = {
        "before": len(options),
        "removed": len(drop),
        "kept": len(keep),
        "names": drop,
    }

    if not drop or dry_run:
        return result

    # ⚠️ 残すものは id ごと渡す。名前だけだと作り直しになり、
    # レコードに付いているタグが外れる
    payload = {
        "properties": {
            prop: {
                "multi_select": {
                    "options": [
                        {"id": o["id"], "name": o["name"], "color": o["color"]}
                        for o in keep
                    ]
                }
            }
        }
    }
    res = await c.patch(f"{API}/data_sources/{ds_id}", json=payload)
    if res.status_code >= 300:
        log.warning("選択肢の整理に失敗 %s: %s", prop, res.text[:200])
        result["removed"] = 0
        result["error"] = res.text[:200]
        return result

    after = await current_options(c, ds_id, prop)
    result["after"] = len(after)
    log.info(
        "%s の選択肢を整理: %d個 → %d個（%d個削除）",
        prop, len(options), len(after), len(drop),
    )
    return result


async def run(dry_run: bool = False) -> Dict[str, int]:
    removed = failed = 0

    async with httpx.AsyncClient(timeout=60, headers=_headers()) as c:
        for db_id, prop in TARGETS:
            if not db_id:
                continue
            try:
                out = await prune_one(c, db_id, prop, dry_run=dry_run)
            except Exception:
                log.exception("選択肢の整理に失敗 %s", prop)
                failed += 1
                continue

            if out.get("error"):
                failed += 1

            print(
                f"  {prop}: {out['before']}個 → 残す{out['kept']}個 / "
                f"消す{out['removed']}個"
            )
            for name in out["names"]:
                print(f"      - {name}")
            removed += out["removed"]

    if dry_run:
        print("\n--dry-run なので実行していません")

    return {"updated": removed, "failed": failed}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="消さずに一覧だけ出す")
    args = parser.parse_args()
    print(asyncio.run(run(args.dry_run)))
