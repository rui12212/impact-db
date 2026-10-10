"""Practice Example の Materials の選択肢を英語に揃える。

  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_fix_materials.py --dry-run
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_fix_materials.py

notion_db_create.py が日本語（写真/動画/授業案/音声）で作ったものを直す。
先生が見る画面に出るため（Botは英語とクメール語のみ）。

⚠️ Notion API の挙動（2026-10-10 に実機で確認）
--------------------------------------------------
1. **選択肢の名前は id を渡しても変更できない。** 無視されてエラーも出ない
2. **`options` はリスト全体の置き換え。** 渡さなかった選択肢は **削除される**

つまり「1つだけ直す」ができない。必ず全選択肢を並べて渡す。
既にページにタグが付いている状態でこれをやるとタグが外れるので、
実行前にページ数を数えて、0件でなければ止める。
"""

from __future__ import annotations

import argparse
import sys

from notion_client import Client

from v2_app.core.config import DB_PRACTICE_EXAMPLE, NOTION_API_KEY

# これが Materials の全選択肢になる。
# apps/practice/schema.py の MATERIAL_BY_KIND の値と一致させること
OPTIONS = ["Photo", "Video", "Audio", "Document"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="ページがあっても実行する（タグが外れる）",
    )
    args = parser.parse_args()

    if not NOTION_API_KEY or not DB_PRACTICE_EXAMPLE:
        print("NOTION_V2_API_KEY / NOTION_V2_PRACTICE_EXAMPLE_DB_ID が未設定です")
        return 1

    notion = Client(auth=NOTION_API_KEY)
    db = notion.databases.retrieve(database_id=DB_PRACTICE_EXAMPLE)
    current = [
        o["name"] for o in db["properties"]["Materials"]["multi_select"]["options"]
    ]

    print(f"現在の選択肢: {current}")
    print(f"あとの選択肢: {OPTIONS}")

    if current == OPTIONS:
        print("\n既に揃っています")
        return 0

    removed = [name for name in current if name not in OPTIONS]
    if removed:
        print(f"\n⚠️ 消える選択肢: {removed}")

    # タグが付いたページがあるなら止める
    res = notion.databases.query(database_id=DB_PRACTICE_EXAMPLE, page_size=1)
    page_count = len(res.get("results", []))
    if page_count and removed and not args.force:
        print(
            "\nページが存在します。消える選択肢があるため中止しました。\n"
            "タグが外れてよいなら --force を付けてください"
        )
        return 1

    if args.dry_run:
        print("\n--dry-run なので実行しません")
        return 0

    # name だけ渡す = 新しい選択肢として作り直す。
    # id を渡して name を変えても無視されるため、これしか手がない
    notion.databases.update(
        database_id=DB_PRACTICE_EXAMPLE,
        properties={
            "Materials": {"multi_select": {"options": [{"name": n} for n in OPTIONS]}}
        },
    )

    db = notion.databases.retrieve(database_id=DB_PRACTICE_EXAMPLE)
    after = [
        o["name"] for o in db["properties"]["Materials"]["multi_select"]["options"]
    ]
    print(f"\n完了: {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
