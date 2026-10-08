"""V2用の Notion データベースを作成するセットアップスクリプト。

前提:
  env/v2.local.env に NOTION_V2_API_KEY と NOTION_V2_ROOT_PAGE_ID を設定しておく
  （ルートページを V2 用インテグレーションに接続しておくこと）

  V1 のキー（NOTION_API_KEY など）は使わない。
  誤って V1 のDBを触らないよう、インテグレーションごと分離する。

  読み込む環境ファイルは V2_ENV_FILE で切り替えられる:
    V2_ENV_FILE=env/v2.prod.env python project/v2_app/scripts/notion_db_create.py

実行:
  python project/v2_app/scripts/notion_db_create.py

特徴:
  - 作成済みのDBは .runtime/v2_db_registry.json に記録し、2回目以降はスキップする
  - リレーションの依存順に作成する
  - 最後に .env へ貼る形でDB IDを出力する

APIで作れないもの（実行後にNotion画面で手作業する）:
  - Unique ID … Notion API は作成に対応していない
  - Rollup    … 最後に案内を出す
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from notion_client import Client

# project/ を import パスに通す（categories.py を読むため）
# このファイルは project/v2_app/scripts/ にあるので、2つ上が project/
PROJECT_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# 環境ファイルは env/ 配下にある（ルートの .env は廃止した）
ENV_FILE = Path(os.getenv("V2_ENV_FILE", "env/v2.local.env"))
if not ENV_FILE.is_absolute():
    ENV_FILE = REPO_ROOT / ENV_FILE

if not ENV_FILE.exists():
    sys.exit(
        f"環境ファイルが見つかりません: {ENV_FILE}\n"
        "NOTION_V2_API_KEY と NOTION_V2_ROOT_PAGE_ID を書いた env/v2.local.env を作成してください。"
    )

load_dotenv(ENV_FILE)

NOTION_V2_API_KEY = os.getenv("NOTION_V2_API_KEY")
ROOT_PAGE_ID = os.getenv("NOTION_V2_ROOT_PAGE_ID")

REGISTRY_PATH = REPO_ROOT / ".runtime" / "v2_db_registry.json"
RATE_LIMIT_SLEEP = 0.4  # Notion API は 3 req/秒


# ---------------------------------------------------------------- registry
def load_registry() -> Dict[str, str]:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {}


def save_registry(reg: Dict[str, str]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------- helpers
def rel(database_id: str, dual: bool = False) -> Dict[str, Any]:
    """リレーションのプロパティ定義。

    dual=True にすると相手のDBにも逆方向のプロパティが自動で作られる。
    親ページ側から子を読みたい場合だけ True にする。
    """
    cfg: Dict[str, Any] = {"database_id": database_id}
    cfg["dual_property" if dual else "single_property"] = {}
    return {"relation": cfg}


def sel(*names: str, colors: Optional[List[str]] = None) -> Dict[str, Any]:
    """Select。引数なしなら選択肢が空の Select を作る（アドミンが後で追加する）。"""
    options: List[Dict[str, str]] = []
    for i, name in enumerate(names):
        option: Dict[str, str] = {"name": name}
        if colors and i < len(colors):
            option["color"] = colors[i]
        options.append(option)
    return {"select": {"options": options}}


def multi(*names: str) -> Dict[str, Any]:
    return {"multi_select": {"options": [{"name": n} for n in names]}}


TITLE: Dict[str, Any] = {"title": {}}
TEXT: Dict[str, Any] = {"rich_text": {}}
NUM: Dict[str, Any] = {"number": {"format": "number"}}
PERCENT: Dict[str, Any] = {"number": {"format": "percent"}}
DATE: Dict[str, Any] = {"date": {}}
CHECK: Dict[str, Any] = {"checkbox": {}}
FILES: Dict[str, Any] = {"files": {}}


def load_category_options() -> List[Dict[str, str]]:
    """categories.py を単一の正として Category の選択肢を組み立てる。"""
    try:
        from impact_app.categorization.categories import category_select_options

        return category_select_options()
    except ImportError as e:
        print(f"  ! categories.py を読めませんでした（{e}）")
        print("    Category は選択肢が空の状態で作成します")
        return []


# ---------------------------------------------------------------- creation
def create_db(
    notion: Client,
    reg: Dict[str, str],
    key: str,
    title: str,
    properties: Dict[str, Any],
) -> str:
    """DBを作成して registry に記録する。既にあればスキップ。"""
    if key in reg:
        print(f"  skip   {title:30} {reg[key][:8]}… (既に作成済み)")
        return reg[key]

    res = notion.databases.create(
        parent={"type": "page_id", "page_id": ROOT_PAGE_ID},
        title=[{"type": "text", "text": {"content": title}}],
        properties=properties,
        is_inline=False,
    )
    reg[key] = res["id"]
    save_registry(reg)
    time.sleep(RATE_LIMIT_SLEEP)
    print(f"  create {title:30} {res['id']}")
    return res["id"]


ENV_NAMES = {
    "school": "NOTION_V2_SCHOOL_DB_ID",
    "user": "NOTION_V2_USER_DB_ID",
    "subject": "NOTION_V2_SUBJECT_DB_ID",
    "school_member": "NOTION_V2_SCHOOL_MEMBER_DB_ID",
    "lesson_study": "NOTION_V2_LESSON_STUDY_DB_ID",
    "practice_example": "NOTION_V2_PRACTICE_EXAMPLE_DB_ID",
    "daily_learning": "NOTION_V2_DAILY_LEARNING_DB_ID",
    "lesson_study_reflection": "NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID",
    "research_question": "NOTION_V2_RESEARCH_QUESTION_DB_ID",
    "teacher_monthly_stats": "NOTION_V2_TEACHER_MONTHLY_STATS_DB_ID",
}


def build_all(notion: Client, reg: Dict[str, str]) -> None:
    print("\n=== STEP 1: 依存なし（School / User / Subject）===")

    school = create_db(notion, reg, "school", "School", {
        "School Name": TITLE,
        "Country": sel("日本", "カンボジア", colors=["blue", "orange"]),
        "Region": sel(),  # 選択肢はアドミンが追加する
    })

    user = create_db(notion, reg, "user", "User", {
        "Teacher Name": TITLE,
        "Role": sel("Teacher", "Admin", "Staff", "Expert",
                    colors=["green", "red", "purple", "yellow"]),
        "Telegram User ID": NUM,
        "Telegram Username": TEXT,
        "Slack ID": TEXT,
    })

    # Subject を参照するのは Practice Example だけ（2026-10-02変更）
    subject = create_db(notion, reg, "subject", "Subject", {
        "Name": TITLE,  # 英語。リレーション検索は Title しか見ない
        "Name KM": TEXT,
        "Schools": rel(school),  # 空なら全校共通
        "Is Active": CHECK,
    })

    print("\n=== STEP 2: School Member ===")

    create_db(notion, reg, "school_member", "School Member", {
        "Name": TITLE,
        "School": rel(school),
        "User": rel(user),
        "Start Date": DATE,
        "End Date": DATE,  # 空 = 在籍中
    })

    print("\n=== STEP 3: Lesson Study ===")

    lesson_study = create_db(notion, reg, "lesson_study", "Lesson Study", {
        "Name": TITLE,
        "Date": DATE,  # 必須はこれだけ。Botが一覧を絞る軸
        "School": rel(school),
        "Subject": TEXT,  # 自由記述。Subject DB は参照しない
        "Grade": TEXT,
        "Teacher Name": TEXT,  # 未登録の先生でも箱を作れるよう文字列で持つ
        "Teacher": rel(user),  # 任意
        "Expert Visit": CHECK,
        "Expert Talk": TEXT,
        "Is Closed": CHECK,  # 未チェック = コメント受付中
        "Image": FILES,
        "Video": FILES,
        "Files": FILES,
    })

    print("\n=== STEP 4: Practice Example ===")

    create_db(notion, reg, "practice_example", "Practice Example", {
        "Title": TITLE,
        "Date": DATE,
        "Teacher": rel(user),
        "School": rel(school),
        "Subject Text": TEXT,
        "Subject": rel(subject),  # Subject を参照する唯一のDB
        "Grade": TEXT,
        "Aim": TEXT,
        "Content": TEXT,
        "Reflection": TEXT,  # やってみてどうだったか（2026-10-02追加）
        "Materials": multi("写真", "動画", "授業案", "音声"),
        "Image": FILES,
        "Video": FILES,
        "Files": FILES,
        "Audio": FILES,
    })

    print("\n=== STEP 5: Daily Learning ===")

    create_db(notion, reg, "daily_learning", "Daily Learning", {
        "Summary": TITLE,
        "Date": DATE,
        "Teacher": rel(user),
        "School": rel(school),
        "Note": TEXT,
        "Subject": TEXT,  # 自由記述。Subject DB は参照しない
        "Keywords": multi(),  # AIが自由に抽出。週次バッチで集計
        "Image": FILES,
        "Video": FILES,
        "Audio": FILES,  # 再文字起こしのために原音を残す
        "Files": FILES,
    })

    print("\n=== STEP 6: Lesson Study Reflection ===")

    create_db(notion, reg, "lesson_study_reflection", "Lesson Study Reflection", {
        "Summary": TITLE,
        "Comment": TEXT,
        "Date": DATE,
        # Lesson Study のページからコメント一覧を見たいので dual
        "Lesson Study": rel(lesson_study, dual=True),
        "Teacher": rel(user),  # コメントを書いた先生
        "School": rel(school),
        "Category": {"select": {"options": load_category_options()}},
        "STT_Km": TEXT,
        "Translated_En": TEXT,
        "Audio": FILES,
        "Image": FILES,
        "Video": FILES,
        "ExternalID": TEXT,  # 重複書き込みの防止
    })

    print("\n=== STEP 7: Research Question ===")

    create_db(notion, reg, "research_question", "Research Question", {
        "RQ": TITLE,
        "Date": DATE,
        "Teacher": rel(user),
        "School": rel(school),
        "Is Current": CHECK,  # 1人に1つだけ true
    })

    print("\n=== STEP 8: Teacher Monthly Stats ===")

    create_db(notion, reg, "teacher_monthly_stats", "Teacher Monthly Stats", {
        "Name": TITLE,
        "User": rel(user),
        "School": rel(school),
        "Period": DATE,  # 月初の日付。積み上げ縦棒グラフのX軸
        "Reflection Count": NUM,
        "Practice Count": NUM,
        "Comment Count": NUM,
    })


# ---------------------------------------------------------------- output
def print_env(reg: Dict[str, str]) -> None:
    print("\n" + "=" * 64)
    print("以下を .env に追記してください")
    print("=" * 64)
    for key, env in ENV_NAMES.items():
        if key in reg:
            print(f"{env}={reg[key]}")


MANUAL_STEPS = """
【1】Unique ID プロパティを追加（9個）
     各DBで「+」→ プロパティタイプ「ID」を選ぶ

       School                     → School ID
       User                       → User ID
       Subject                    → Subject ID
       School Member              → Member ID
       Lesson Study               → Lesson Study ID
       Practice Example           → Practice ID
       Daily Learning             → Learning ID
       Lesson Study Reflection    → Lesson Study Reflection ID
       Research Question          → RQ ID

     ※ Teacher Monthly Stats は不要（バッチが作るだけのため）

【2】Rollup を追加（5個）
     計算方法はいずれも「元の値を表示 / Show original」

       Lesson Study Reflection
         Lesson Study Date         ← Lesson Study の Date
         Lesson Study Subject      ← Lesson Study の Subject
         Lesson Study Grade        ← Lesson Study の Grade
         Lesson Study Expert Visit ← Lesson Study の Expert Visit

       School Member
         Teacher Name         ← User の Teacher Name

【3】逆方向リレーションの名前を整える
     dual_property で自動生成された名前を変更する

       Lesson Study 側 → Reflections

【4】Subject にマスタデータを登録
     Name（英語）/ Name KM を入れ、Is Active にチェック
     ※ 先方から教科の一覧をいただいたら差し替える

【5】Subject に「要確認」ビューを作成
     フィルタ: Name KM が空
     → Notion画面で誤って作られた教科を検出するため

【6】Lesson Study の編集権限をアドミン/スタッフのみに設定
     先生に新しい授業研究を作らせないため（紐付けの乱れ防止）
"""


def print_manual_steps() -> None:
    print("\n" + "=" * 64)
    print("Notion画面での手作業（APIでは設定できないもの）")
    print("=" * 64)
    print(MANUAL_STEPS)


# ---------------------------------------------------------------- main
def main() -> None:
    if not NOTION_V2_API_KEY:
        sys.exit("NOTION_V2_API_KEY が設定されていません（.env を確認してください）")
    if not ROOT_PAGE_ID:
        sys.exit("NOTION_V2_ROOT_PAGE_ID が設定されていません（.env を確認してください）")

    notion = Client(auth=NOTION_V2_API_KEY)
    reg = load_registry()

    print(f"環境ファイル: {ENV_FILE}")
    print(f"ルートページ: {ROOT_PAGE_ID}")
    print(f"registry    : {REGISTRY_PATH}")

    try:
        build_all(notion, reg)
    except Exception as e:
        print(f"\n作成に失敗しました: {e}")
        print("\nよくある原因:")
        print("  - ルートページを V2 用インテグレーションに接続していない")
        print("    → ページ右上「…」→ 接続 → V2用インテグレーションを追加")
        print("  - V1 のインテグレーションに接続してしまっている")
        print("    → NOTION_V2_API_KEY と、接続したインテグレーションが一致しているか確認")
        print("  - NOTION_V2_ROOT_PAGE_ID が正しくない")
        print("    → URLのタイトル以降32文字。?v= 以降は含めない")
        print(f"\n作成済みのDBは {REGISTRY_PATH} に記録されています。")
        print("修正して再実行すれば、続きから作成されます。")
        sys.exit(1)

    print_env(reg)
    print_manual_steps()


if __name__ == "__main__":
    main()
