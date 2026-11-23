"""2026-10-02 の設計変更を既存の Notion DB に反映する一回限りのスクリプト。

変更内容:
  ① Learning Journey → Lesson Study に改名（DB名・プロパティ名・リレーション名）
  ② Learning Journey Reflection → Lesson Study Reflection に改名
  ③ Subject DB への参照を Practice Example だけにする
       Daily Learning  : Subject（リレーション）を削除
       Lesson Study    : Subject をリレーションから Rich text へ
  ④ Daily Learning の Practice Example リレーションを削除
       （実践後の振り返りは Practice Example の Reflection に1項目で持つ）
  ⑤ Practice Example に Reflection（Rich text）を追加
  ⑥ Lesson Study から Image / Video / Files を削除
  ⑦ Lesson Study Reflection から Level Value / Files を削除
  ⑧ Category の選択肢を8分類に更新（categories.py が単一の正）
  ⑨ Subject に Schools（Relation → School・複数）を追加
  ⑩ Teacher Monthly Stats から Record Rate を削除

実行:
  docker compose -f docker/v2.local.yml exec app \\
    python project/v2_app/scripts/notion_db_migrate_20261002.py

  確認だけしたい場合:
  docker compose -f docker/v2.local.yml exec app \\
    python project/v2_app/scripts/notion_db_migrate_20261002.py --dry-run

注意:
  - データが入る前に実行する前提。プロパティ削除は中身も消える
  - registry のキー learning_journey / lj_reflection はこのスクリプトでは変えない
    （別途 rename_registry_keys() を最後に呼んで書き換える）
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

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


def load_registry() -> Dict[str, str]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def category_options() -> List[Dict[str, str]]:
    from impact_app.categorization.categories import category_select_options

    return category_select_options()


# ---------------------------------------------------------------- 操作
def update_db(notion: Client, db_id: str, label: str, **kwargs: Any) -> None:
    if DRY_RUN:
        print(f"  [dry-run] {label}")
        return
    notion.databases.update(database_id=db_id, **kwargs)
    time.sleep(SLEEP)
    print(f"  ok  {label}")


def rename_db(notion: Client, db_id: str, new_title: str) -> None:
    update_db(
        notion, db_id, f"DB名を「{new_title}」に変更",
        title=[{"type": "text", "text": {"content": new_title}}],
    )


def rename_props(notion: Client, db_id: str, mapping: Dict[str, str]) -> None:
    """{旧名: 新名} でプロパティを改名する。"""
    for old, new in mapping.items():
        update_db(
            notion, db_id, f"プロパティ {old} → {new}",
            properties={old: {"name": new}},
        )


def delete_props(notion: Client, db_id: str, names: List[str]) -> None:
    for name in names:
        update_db(
            notion, db_id, f"プロパティ {name} を削除",
            properties={name: None},
        )


def add_props(notion: Client, db_id: str, props: Dict[str, Any]) -> None:
    for name, spec in props.items():
        update_db(
            notion, db_id, f"プロパティ {name} を追加",
            properties={name: spec},
        )


# ---------------------------------------------------------------- 本体
def migrate(notion: Client, reg: Dict[str, str]) -> None:
    school = reg["school"]
    subject = reg["subject"]
    journey = reg["learning_journey"]
    reflection = reg["lj_reflection"]
    daily = reg["daily_learning"]
    practice = reg["practice_example"]
    stats = reg["teacher_monthly_stats"]

    # ---------- ① Lesson Study へ改名 ----------
    print("\n[1] Learning Journey → Lesson Study")
    rename_db(notion, journey, "Lesson Study")
    rename_props(notion, journey, {"Journey ID": "Lesson Study ID"})

    # ---------- ⑥ Lesson Study からメディアを削除 ----------
    print("\n[2] Lesson Study からメディアを削除")
    delete_props(notion, journey, ["Image", "Video", "Files"])

    # ---------- ③ Lesson Study の Subject をリレーション → Rich text ----------
    # 型変更は直接できないため、削除してから作り直す
    print("\n[3] Lesson Study の Subject を自由記述に")
    delete_props(notion, journey, ["Subject"])
    add_props(notion, journey, {"Subject": {"rich_text": {}}})

    # ---------- ② Lesson Study Reflection へ改名 ----------
    # リレーションを先に改名する。ロールアップは内部でidを持つため追随する
    print("\n[4] Learning Journey Reflection → Lesson Study Reflection")
    rename_db(notion, reflection, "Lesson Study Reflection")
    rename_props(notion, reflection, {
        "Reflection ID": "Lesson Study Reflection ID",
        "Learning Journey": "Lesson Study",
    })
    rename_props(notion, reflection, {
        "Journey Date": "Lesson Study Date",
        "Journey Subject": "Lesson Study Subject",
        "Journey Grade": "Lesson Study Grade",
        "Journey Expert Visit": "Lesson Study Expert Visit",
    })

    # ---------- ⑦ 不要プロパティの削除 ----------
    print("\n[5] Lesson Study Reflection から Level Value / Files を削除")
    delete_props(notion, reflection, ["Level Value", "Files"])

    # ---------- ⑧ Category を8分類に ----------
    print("\n[6] Category の選択肢を8分類に更新")
    opts = category_options()
    for o in opts:
        print(f"      {o['name']:34} {o['color']}")
    update_db(
        notion, reflection, "Category の選択肢を差し替え",
        properties={"Category": {"select": {"options": opts}}},
    )

    # ---------- ③④ Daily Learning ----------
    print("\n[7] Daily Learning から Subject / Practice Example を削除")
    # Practice Example は dual_property。削除すると Practice Example 側の
    # Reflections も自動で消える
    delete_props(notion, daily, ["Subject", "Practice Example"])

    # ---------- ⑤ Practice Example に Reflection ----------
    print("\n[8] Practice Example に Reflection を追加")
    add_props(notion, practice, {"Reflection": {"rich_text": {}}})

    # ---------- ⑨ Subject に Schools ----------
    print("\n[9] Subject に Schools を追加")
    add_props(notion, subject, {
        "Schools": {"relation": {"database_id": school, "single_property": {}}}
    })

    # ---------- ⑩ Teacher Monthly Stats ----------
    print("\n[10] Teacher Monthly Stats から Record Rate を削除")
    delete_props(notion, stats, ["Record Rate"])


def rename_registry_keys() -> None:
    """registry のキーを新しい名前に合わせる。"""
    reg = load_registry()
    mapping = {
        "learning_journey": "lesson_study",
        "lj_reflection": "lesson_study_reflection",
    }
    changed = False
    for old, new in mapping.items():
        if old in reg:
            reg[new] = reg.pop(old)
            changed = True
            print(f"  registry: {old} → {new}")
    if changed and not DRY_RUN:
        REGISTRY_PATH.write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8"
        )


NEXT_STEPS = """
================================================================
このスクリプトの後にやること
================================================================

【1】env/v2.local.env の変数名を変更
     NOTION_V2_LEARNING_JOURNEY_DB_ID  → NOTION_V2_LESSON_STUDY_DB_ID
     NOTION_V2_LJ_REFLECTION_DB_ID     → NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID
     （値はそのまま）

【2】Notion画面で確認
     - Lesson Study Reflection の Category が8色になっているか
     - ロールアップ4つの参照先が残っているか
       （リレーション名を変えたので、外れていないか目視確認）
     - Subject の Schools に学校を紐づける（空なら全校共通）

【3】notion_db_verify.py を実行して突き合わせる

【4】Lesson Study Reflection に Unique ID が残っているか
     改名したので名前が変わっている。Lesson Study Reflection ID になっているか
"""


def main() -> None:
    if not NOTION_V2_API_KEY:
        sys.exit("NOTION_V2_API_KEY が設定されていません")
    if not REGISTRY_PATH.exists():
        sys.exit(f"registry が見つかりません: {REGISTRY_PATH}")

    notion = Client(auth=NOTION_V2_API_KEY)
    reg = load_registry()

    if DRY_RUN:
        print("=== dry-run（Notionには何も書き込みません）===")

    print(f"環境ファイル: {ENV_FILE}")
    print(f"registry    : {REGISTRY_PATH}")

    try:
        migrate(notion, reg)
    except Exception as e:  # noqa: BLE001
        print(f"\n失敗しました: {e}")
        print("\nこのスクリプトは途中まで適用された状態で止まります。")
        print("原因を直して再実行すると、既に済んだ操作は再度実行されますが、")
        print("改名・削除・追加はいずれも冪等なので問題ありません")
        print("（既に無いプロパティの削除はエラーになるため、その行は飛ばしてください）。")
        sys.exit(1)

    print("\n[11] registry のキーを更新")
    rename_registry_keys()

    print(NEXT_STEPS)


if __name__ == "__main__":
    main()
