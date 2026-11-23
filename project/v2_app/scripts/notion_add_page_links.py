"""User と School に「そのページのURL」を持たせるプロパティを足す。

  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_add_page_links.py --dry-run
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_add_page_links.py

なぜ必要か:
  バッチ（keywords.py / ai_summary.py）が「この先生のマイページはどれか」を
  知る方法が今ない。ページのブロックを書き換えるには page id が必要。

  Notion には「任意のページへのリレーション」という型が無いので URL で持つ。
  URL の末尾32文字が page id なので、そこから復元できる。
  URLで持つと、アドミンがNotionの一覧から直接開けるという利点もある。

誰が書くか:
  scripts/notion_page_create.py がページを作った時に書き込む。

⚠️ databases.update の properties は**名前をキーにしたマージ**。
   渡さなかったプロパティは消えない。
   （select の options だけが全置き換えで、そこは別の話 → guide §9 #9）
"""

from __future__ import annotations

import argparse
import sys

import os
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client

# ⚠️ **V2_ENV_FILE を見る。** config から読むだけだと、コンテナに
# 注入された環境変数（= 開発）を使ってしまい、本番に足したつもりで
# **開発のDBを見ていた**（2026-10-22に発覚）。
#
#   V2_ENV_FILE=env/v2.prod.env で本番、省略すると compose の env
#
# override=True が必須。注入済みの値が勝つと指定が無意味になる
_ENV_FILE = Path(os.getenv("V2_ENV_FILE", ""))
if _ENV_FILE:
    if not _ENV_FILE.is_absolute():
        _ENV_FILE = Path("/app") / _ENV_FILE
    if not _ENV_FILE.exists():
        raise SystemExit(f"環境ファイルが見つかりません: {_ENV_FILE}")
    load_dotenv(_ENV_FILE, override=True)

DB_SCHOOL = os.getenv("NOTION_V2_SCHOOL_DB_ID", "")
DB_USER = os.getenv("NOTION_V2_USER_DB_ID", "")
NOTION_API_KEY = os.getenv("NOTION_V2_API_KEY", "")

# (DB, 足すプロパティ名, 説明)
TARGETS = [
    (DB_USER, "Mypage", "先生のマイページのURL"),
    (DB_SCHOOL, "Schoolpage", "スクールページのURL"),
    # マイページを学校ごとのフォルダに分ける（2026-10-21）。
    # 外部校が入ってくるので、先生が他校のページへ行けないようにする。
    # ⚠️ タイトルで探すのではなく**URLで覚える。**
    #    学校名を変えると別のフォルダが作られてしまう
    (DB_SCHOOL, "Mypagefolder", "その学校のマイページを入れるフォルダのURL"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not NOTION_API_KEY:
        print("NOTION_V2_API_KEY が未設定")
        return 1

    notion = Client(auth=NOTION_API_KEY)
    todo = []

    # ⚠️ **どこを触るかを出す。** IDの文字列は見比べても間違いに
    # 気づけないので、環境ファイルとDBの末尾を並べる
    print(f"env ファイル : {_ENV_FILE or '（compose の env）'}")
    print(f"School DB    : ...{DB_SCHOOL[-6:]}")
    print(f"User DB      : ...{DB_USER[-6:]}")
    print()

    for db_id, prop_name, note in TARGETS:
        db = notion.databases.retrieve(database_id=db_id)
        title = "".join(t.get("plain_text", "") for t in db.get("title", []))
        existing = list(db["properties"])

        if prop_name in existing:
            print(f"{title}: {prop_name} は既にあります（{len(existing)}プロパティ）")
            continue

        print(f"{title}: {prop_name} を足します（{note}）")
        print(f"  現在 {len(existing)}プロパティ: {existing}")
        todo.append((db_id, title, prop_name, len(existing)))

    if not todo:
        print("\n足すものはありません")
        return 0

    if args.dry_run:
        print("\n--dry-run なので実行しません")
        return 0

    for db_id, title, prop_name, before in todo:
        notion.databases.update(
            database_id=db_id,
            properties={prop_name: {"url": {}}},
        )
        db = notion.databases.retrieve(database_id=db_id)
        after = list(db["properties"])
        ok = prop_name in after and len(after) == before + 1
        mark = "OK" if ok else "⚠️"
        print(f"\n[{mark}] {title}: {before} → {len(after)}プロパティ")
        if not ok:
            print(f"      {after}")

    print("\n完了。notion_db_create.py と notion_db_verify.py も直してください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
