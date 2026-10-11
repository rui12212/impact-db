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

from notion_client import Client

from v2_app.core.config import DB_SCHOOL, DB_USER, NOTION_API_KEY

# (DB, 足すプロパティ名, 説明)
TARGETS = [
    (DB_USER, "Mypage", "先生のマイページのURL"),
    (DB_SCHOOL, "Schoolpage", "スクールページのURL"),
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
