"""notion_db_migrate_20261002.py の実行後に出た修正を当てるスクリプト。

修正内容:
  ① Lesson Study に Image / Video / Files を戻す
       後から使う可能性があるため、削除を取り消す
  ② Daily Learning の Subject Text → Subject に改名
       リレーションが無くなり "Text" の対になるものが消えたため。
       Lesson Study と名前を揃える
       （Practice Example は Subject Text + Subject の両方を持つので触らない）

実行:
  docker compose -f docker/v2.local.yml exec app \\
    python project/v2_app/scripts/notion_db_fix_20261002.py

  確認だけ:
  docker compose -f docker/v2.local.yml exec app \\
    python project/v2_app/scripts/notion_db_fix_20261002.py --dry-run

何度実行しても同じ結果になる（冪等）:
  - 既にあるプロパティの追加は Notion 側で上書きになるだけ
  - 既に改名済みなら「見つからない」で飛ばす
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from notion_client import Client

PROJECT_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

ENV_FILE = Path(os.getenv("V2_ENV_FILE", "env/v2.local.env"))
if not ENV_FILE.is_absolute():
    ENV_FILE = REPO_ROOT / ENV_FILE
load_dotenv(ENV_FILE)

NOTION_V2_API_KEY = os.getenv("NOTION_V2_API_KEY")
REGISTRY_PATH = REPO_ROOT / ".runtime" / "v2_db_registry.json"
SLEEP = 0.4
DRY_RUN = "--dry-run" in sys.argv

FILES: Dict[str, Any] = {"files": {}}
TEXT: Dict[str, Any] = {"rich_text": {}}


def update_db(notion: Client, db_id: str, label: str, **kwargs: Any) -> None:
    if DRY_RUN:
        print(f"  [dry-run] {label}")
        return
    notion.databases.update(database_id=db_id, **kwargs)
    time.sleep(SLEEP)
    print(f"  ok  {label}")


def main() -> None:
    if not NOTION_V2_API_KEY:
        sys.exit("NOTION_V2_API_KEY が設定されていません")
    if not REGISTRY_PATH.exists():
        sys.exit(f"registry が見つかりません: {REGISTRY_PATH}")

    notion = Client(auth=NOTION_V2_API_KEY)
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    if DRY_RUN:
        print("=== dry-run（Notionには何も書き込みません）===")
    print(f"環境ファイル: {ENV_FILE}")

    lesson_study = reg["lesson_study"]
    daily = reg["daily_learning"]

    # ---------- ① Lesson Study にメディアを戻す ----------
    print("\n[1] Lesson Study に Image / Video / Files を戻す")
    for name in ("Image", "Video", "Files"):
        update_db(notion, lesson_study, f"プロパティ {name} を追加",
                  properties={name: FILES})

    # ---------- ② Daily Learning の Subject Text → Subject ----------
    print("\n[2] Daily Learning の Subject Text → Subject")
    db = notion.databases.retrieve(database_id=daily)
    props = db.get("properties", {})

    if "Subject" in props:
        print("  skip  Subject が既にある（改名済み）")
    elif "Subject Text" not in props:
        print("  warn  Subject Text も Subject も無い。手動で確認してください")
    else:
        update_db(notion, daily, "プロパティ Subject Text → Subject",
                  properties={"Subject Text": {"name": "Subject"}})

    print("""
================================================================
この後にやること
================================================================

【1】env/v2.local.env の変数名を2つ変更（値はそのまま）
     NOTION_V2_LEARNING_JOURNEY_DB_ID → NOTION_V2_LESSON_STUDY_DB_ID
     NOTION_V2_LJ_REFLECTION_DB_ID    → NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID

【2】Notion画面で確認
     - Lesson Study Reflection のロールアップ4つの参照先が外れていないか
       （リレーション名を Learning Journey → Lesson Study に変えたため）
     - Lesson Study Reflection の Unique ID が
       「Lesson Study Reflection ID」になっているか
     - Category が8色になっているか
     - Subject の Schools に学校を紐づける（空なら全校共通）

【3】検証
     python project/v2_app/scripts/notion_db_verify.py
""")


if __name__ == "__main__":
    main()
