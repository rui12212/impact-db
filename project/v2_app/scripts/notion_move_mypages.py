"""マイページを学校ごとのフォルダに移す。

  # 何がどこへ移るか見るだけ（Notionに書かない）
  docker compose -f docker/v2.local.yml exec \
      -e V2_ENV_FILE=env/v2.prod.env app \
      python -m v2_app.scripts.notion_move_mypages --dry-run

  # 実行
  docker compose -f docker/v2.local.yml exec \
      -e V2_ENV_FILE=env/v2.prod.env app \
      python -m v2_app.scripts.notion_move_mypages

  # 1人だけ
  ... --only <telegram_id>

なぜ必要か（2026-10-21決定）:
  外部校が入ってくるので、**先生が他校のマイページへ行けないように**
  学校ごとのフォルダに分ける。Notion の権限はページの階層に沿って
  降りるので、フォルダに招待すればその学校の中だけが見える。

  ⚠️ **Notion にページを移動するAPIが無い。** 作り直して
  `User.Mypage` を差し替え、古いページをゴミ箱に入れる。

⚠️ 移行後にやること
  1. バッチを回して文章を埋め直す（AIサマリー・キーワード・問い）
       python -m v2_app.batch.runner all
  2. **ゲスト招待をやり直す。** 古いページへの招待は引き継がれない。
     学校フォルダに招待すれば、その学校の先生の分がまとまる

⚠️ 消えるもの / 消えないもの
  消える   ページの中のAIの文章（→ バッチで戻る）
  消えない 先生の記録（Daily Learning など。別のDBにある）
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

# ⚠️ **V2_ENV_FILE を見る。** config から読むだけだと、コンテナに
# 注入された環境変数（= 開発）を使ってしまい、開発を触ったつもりで
# 本番を直す（あるいは逆）という事故になる。override=True が必須
_ENV_FILE = os.getenv("V2_ENV_FILE", "")
if _ENV_FILE:
    path = _ENV_FILE if os.path.isabs(_ENV_FILE) else f"/app/{_ENV_FILE}"
    if not os.path.exists(path):
        raise SystemExit(f"環境ファイルが見つかりません: {path}")
    load_dotenv(path, override=True)

log = logging.getLogger("impactdb.v2")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="書かずに一覧だけ")
    parser.add_argument("--only", type=int, help="この telegram_id の先生だけ")
    args = parser.parse_args()

    # ⚠️ import はここで。load_dotenv より先に config を読ませない
    from v2_app.core import page_layout as pl
    from v2_app.core.notion_client import get_notion, update_page
    from v2_app.scripts.notion_page_create import (
        build,
        ensure_school_folder,
        school_names,
        teachers,
    )

    root = os.getenv("NOTION_V2_MYPAGE_ROOT_ID")
    if not root:
        print("NOTION_V2_MYPAGE_ROOT_ID が未設定")
        return 1

    notion = get_notion()
    rows = await teachers()
    if args.only is not None:
        rows = [t for t in rows if t["telegram_id"] == args.only]

    schools = await school_names()

    # --- どこを触るか見せる ---
    page = await notion.pages.retrieve(page_id=root)
    items = page.get("properties", {}).get("title", {}).get("title", [])
    root_title = "".join(i.get("plain_text", "") for i in items) or "(無題)"

    print()
    print("=" * 60)
    print(f"  env ファイル : {_ENV_FILE or '（compose の env）'}")
    print(f"  親ページ     : {root_title}")
    print(f"  先生         : {len(rows)}人")
    print("=" * 60)
    print()

    todo: List[Dict[str, Any]] = []
    for teacher in rows:
        name = teacher["name"]
        school = schools.get(teacher["school_id"], "")
        page_id = pl.page_id_from_url(teacher["mypage"])

        if not teacher["school_id"]:
            print(f"  skip   {name:20} 在籍中の学校が無い")
            continue
        if not page_id:
            print(f"  new    {name:20} マイページが無い → {school} に作る")
            todo.append({"teacher": teacher, "school": school, "old": ""})
            continue

        # 既にフォルダの中にいるか
        info = await notion.pages.retrieve(page_id=page_id)
        parent = info.get("parent", {}).get("page_id", "")
        if parent and parent.replace("-", "") != root.replace("-", ""):
            print(f"  ok     {name:20} 既にフォルダの中")
            continue

        print(f"  move   {name:20} {school} のフォルダへ")
        todo.append({"teacher": teacher, "school": school, "old": page_id})

    if not todo:
        print("\n移すものはありません")
        return 0

    print(f"\n{len(todo)}人を移します。1人あたり約46回のAPI呼び出し。")
    if args.dry_run:
        print("--dry-run なので実行しません")
        return 0

    answer = input("続けますか [y/N]: ").strip().lower()
    if answer != "y":
        print("中止しました")
        return 1

    moved = failed = 0
    for item in todo:
        teacher = item["teacher"]
        name = teacher["name"]
        try:
            folder = await ensure_school_folder(teacher["school_id"])
            if not folder:
                print(f"  NG     {name:20} フォルダを作れない")
                failed += 1
                continue

            new_page = await notion.pages.create(
                parent={"type": "page_id", "page_id": folder},
                icon={"type": "emoji", "emoji": "🌱"},
                properties={"title": {"title": [{"text": {"content": name}}]}},
            )
            await build(new_page["id"], teacher, item["school"])
            await update_page(
                teacher["user_id"], {"Mypage": {"url": new_page["url"]}}
            )

            # ⚠️ URLを差し替えたあとに消す。順番を逆にすると、
            # 途中で落ちた時に**どこも指していないマイページ**になる
            if item["old"]:
                await notion.pages.update(page_id=item["old"], archived=True)

            print(f"  OK     {name:20} {new_page['url']}")
            moved += 1
        except Exception as e:
            print(f"  NG     {name:20} {str(e)[:80]}")
            log.exception("移行に失敗 %s", name)
            failed += 1

    print(f"\n移した {moved}人 / 失敗 {failed}人")
    print("\nこのあと:")
    print("  1. バッチで文章を埋め直す")
    print("       python -m v2_app.batch.runner all")
    print("  2. **ゲスト招待をやり直す**（学校フォルダに招待する）")
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    raise SystemExit(asyncio.run(main()))
