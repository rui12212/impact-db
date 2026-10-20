"""User に「設定で選んだ言語」を持たせるプロパティを足す。

  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_add_language.py --dry-run
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/notion_add_language.py

なぜ必要か:
  日本語入力に対応するため、先生ごとに言語を持つ必要がある
  （→ modify/2026-10-20-japanese-input-language-design.md）。

  Redis だけに持つと**コンテナを止めた時に消え**、端末の言語設定に
  戻ってしまう。Notion を正本にする（2026-10-20決定）。

誰が書くか:
  設定モードで先生が選んだ時に user_repo.set_language が書き込む。
  空のままなら Telegram の言語コードに落とす（core/lang.py）。

⚠️ databases.update の properties は**名前をキーにしたマージ**。
   渡さなかったプロパティは消えない。
   ただし **select の options はリスト全体の置き換え**なので、
   既にこのプロパティがある場合は選択肢を上書きしないよう何もしない。
"""

from __future__ import annotations

import argparse
import sys

from notion_client import Client

from v2_app.core.config import DB_USER, NOTION_API_KEY
from v2_app.core.lang import SUPPORTED

PROP = "Language"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not NOTION_API_KEY or not DB_USER:
        print("NOTION_V2_API_KEY / NOTION_V2_USER_DB_ID が未設定")
        return 1

    notion = Client(auth=NOTION_API_KEY)
    db = notion.databases.retrieve(database_id=DB_USER)
    title = "".join(t.get("plain_text", "") for t in db.get("title", []))
    existing = list(db["properties"])

    if PROP in existing:
        options = [
            o["name"]
            for o in db["properties"][PROP].get("select", {}).get("options", [])
        ]
        print(f"{title}: {PROP} は既にあります（選択肢: {options}）")
        missing = [c for c in SUPPORTED if c not in options]
        if missing:
            print(f"  ⚠️ 選択肢が足りません: {missing}")
            print("     Notion の画面で足してください（options を API から")
            print("     渡すとリスト全体の置き換えになり、既存の選択肢が消えます）")
        return 0

    print(f"{title}: {PROP} を足します（設定で選んだ言語）")
    print(f"  現在 {len(existing)}プロパティ: {existing}")
    print(f"  選択肢: {list(SUPPORTED)}")

    if args.dry_run:
        print("\n--dry-run なので実行しません")
        return 0

    notion.databases.update(
        database_id=DB_USER,
        properties={
            PROP: {
                "select": {"options": [{"name": code} for code in SUPPORTED]}
            }
        },
    )

    db = notion.databases.retrieve(database_id=DB_USER)
    after = list(db["properties"])
    options = [
        o["name"] for o in db["properties"][PROP].get("select", {}).get("options", [])
    ]
    print(f"\n完了: {len(after)}プロパティ / {PROP} の選択肢 {options}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
