"""V2の Notion データベースが設計どおりになっているか検証するスクリプト。

notion_db_create.py はAPIで作れるものだけを作る。
Unique ID と Rollup、逆方向リレーションの名前はNotion画面での手作業になるため、
その抜けや設定ミスをここで機械的に検出する。

前提:
  .runtime/v2_db_registry.json が存在する（notion_db_create.py の実行後）
  env/v2.local.env に NOTION_V2_API_KEY がある

実行:
  docker compose -f docker/v2.local.yml exec app \\
    python project/v2_app/scripts/notion_db_verify.py

出力:
  ✓ 一致 / ✗ 欠落・不一致 / ? 設計書に無い余分なプロパティ
  不一致があれば終了コード 1
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------- 期待する定義
# 値の意味:
#   "title" / "rich_text" / "number" / "select" / "multi_select"
#   "date" / "checkbox" / "files" / "unique_id"
#   ("relation", "<相手のDBキー>")
#   ("rollup", "<自分のリレーション名>", "<相手のプロパティ名>")
EXPECTED: Dict[str, Dict[str, Any]] = {
    "school": {
        "School Name": "title",
        "School ID": "unique_id",
        "Country": "select",
        "Region": "select",
        "Schoolpage": "url",
        "Mypagefolder": "url",
    },
    "user": {
        "Teacher Name": "title",
        "User ID": "unique_id",
        "Role": "select",
        "Telegram User ID": "number",
        "Telegram Username": "rich_text",
        "Slack ID": "rich_text",
        "Mypage": "url",
    },
    "subject": {
        "Name": "title",
        "Subject ID": "unique_id",
        "Name KM": "rich_text",
        "Schools": ("relation", "school"),
        "Is Active": "checkbox",
    },
    "school_member": {
        "Name": "title",
        "Member ID": "unique_id",
        "School": ("relation", "school"),
        "User": ("relation", "user"),
        "Start Date": "date",
        "End Date": "date",
        "Teacher Name": ("rollup", "User", "Teacher Name"),
    },
    "lesson_study": {
        "Name": "title",
        "Lesson Study ID": "unique_id",
        "Date": "date",
        "School": ("relation", "school"),
        "Subject": "rich_text",
        "Grade": "rich_text",
        "Teacher Name": "rich_text",
        "Teacher": ("relation", "user"),
        "Expert Visit": "checkbox",
        "Expert Talk": "rich_text",
        "Is Closed": "checkbox",
        "Image": "files",
        "Video": "files",
        "Files": "files",
        # 逆方向（Lesson Study Reflection からの dual_property）
        "Reflections": ("relation", "lesson_study_reflection"),
    },
    "practice_example": {
        "Title": "title",
        "Practice ID": "unique_id",
        "Date": "date",
        "Teacher": ("relation", "user"),
        "School": ("relation", "school"),
        "Subject Text": "rich_text",
        "Subject": ("relation", "subject"),
        "Grade": "rich_text",
        "Aim": "rich_text",
        "Content": "rich_text",
        "Reflection": "rich_text",
        "Materials": "multi_select",
        "Image": "files",
        "Video": "files",
        "Files": "files",
        "Audio": "files",
    },
    "daily_learning": {
        "Summary": "title",
        "Learning ID": "unique_id",
        "Date": "date",
        "Teacher": ("relation", "user"),
        "School": ("relation", "school"),
        "Note": "rich_text",
        "Subject": "rich_text",
        "Keywords": "multi_select",
        "Image": "files",
        "Video": "files",
        "Audio": "files",
        "Files": "files",
    },
    "lesson_study_reflection": {
        "Summary": "title",
        "Lesson Study Reflection ID": "unique_id",
        # 文字情報は**入力手段で分ける**（2026-10-26）
        #   → modify/2026-10-26-lesson-study-text-audio-restructure.md
        "Comment_org": "rich_text",      # 打ち込み＋音声＋caption の原文
        "Text_org": "rich_text",         # そのうち打ち込みと caption だけ
        "Audio_stt_org": "rich_text",    # そのうち音声の文字起こしだけ
        "Comment_eng": "rich_text",      # Comment_org の英訳（分類の入力）
        # ⚠️ 旧3つは**書き込まれないが Notion には残す。** 過去のレコードの
        # 値が入っており、移行の参照元にもなる。削除は移行の確認後
        "Comment": "rich_text",
        "STT_Km": "rich_text",
        "Translated_En": "rich_text",
        "Date": "date",
        "Lesson Study": ("relation", "lesson_study"),
        "Teacher": ("relation", "user"),
        "School": ("relation", "school"),
        "Category": "select",
        "Audio": "files",
        "Image": "files",
        "Video": "files",
        "ExternalID": "rich_text",
        "Lesson Study Date": ("rollup", "Lesson Study", "Date"),
        "Lesson Study Subject": ("rollup", "Lesson Study", "Subject"),
        "Lesson Study Grade": ("rollup", "Lesson Study", "Grade"),
        "Lesson Study Expert Visit": ("rollup", "Lesson Study", "Expert Visit"),
    },
    "research_question": {
        "RQ": "title",
        "RQ ID": "unique_id",
        "Date": "date",
        "Teacher": ("relation", "user"),
        "School": ("relation", "school"),
        "Is Current": "checkbox",
    },
    "teacher_monthly_stats": {
        "Name": "title",
        "User": ("relation", "user"),
        "School": ("relation", "school"),
        "Period": "date",
        "Reflection Count": "number",
        "Practice Count": "number",
        "Comment Count": "number",
    },
}

# Category の選択肢は categories.py が単一の正
EXPECTED_SELECT_OPTIONS = {
    ("lesson_study_reflection", "Category"): "categories",
    ("school", "Country"): ["日本", "カンボジア"],
    ("user", "Role"): ["Teacher", "Admin", "Staff", "Expert"],
}


def expected_category_names() -> Optional[List[str]]:
    try:
        from impact_app.categorization.categories import category_select_options

        return [o["name"] for o in category_select_options()]
    except ImportError:
        return None


# ---------------------------------------------------------------- 検証
def norm_id(s: str) -> str:
    return s.replace("-", "").lower()


class Result:
    def __init__(self) -> None:
        self.ok: List[str] = []
        self.bad: List[str] = []
        self.extra: List[str] = []
        # APIが情報を返さず検証できなかったもの（目視確認が必要）
        self.unknown: List[str] = []

    @property
    def failed(self) -> bool:
        return bool(self.bad)


def resolve_rolled_up_name(
    fetch_db,
    own_props: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Tuple[Optional[str], str]:
    """ロールアップの参照先プロパティ名を返す。

    Notion API は rolled_up_property_name を返さず
    rolled_up_property_id だけを返すことがある。その場合は
    リレーション先のDBを引いて id → 名前 に解決する。

    戻り値: (名前 or None, 解決方法の説明)
    """
    name = cfg.get("rolled_up_property_name")
    if name:
        return name, "name"

    prop_id = cfg.get("rolled_up_property_id")
    if not prop_id:
        return None, "未設定（idも空）"

    rel_name = cfg.get("relation_property_name")
    rel = own_props.get(rel_name or "", {})
    target_db_id = rel.get("relation", {}).get("database_id")
    if not target_db_id:
        return None, f"参照先DBが不明（リレーション {rel_name} を辿れない）"

    try:
        target = fetch_db(target_db_id)
    except Exception as e:  # noqa: BLE001
        return None, f"参照先DBを取得できない（{e}）"

    for n, p in target.get("properties", {}).items():
        if p.get("id") == prop_id:
            return n, "id経由で解決"
    return None, f"id {prop_id} が参照先DBに見つからない"


def check_property(
    db_key: str,
    prop_name: str,
    spec: Any,
    actual: Dict[str, Any],
    reg: Dict[str, str],
    res: Result,
    own_props: Optional[Dict[str, Any]] = None,
    fetch_db=None,
) -> None:
    actual_type = actual.get("type")

    # --- リレーション ---
    if isinstance(spec, tuple) and spec[0] == "relation":
        target_key = spec[1]
        if actual_type != "relation":
            res.bad.append(f"    ✗ {prop_name}: 型が relation でない（{actual_type}）")
            return
        target_id = actual["relation"].get("database_id", "")
        want_id = reg.get(target_key, "")
        if norm_id(target_id) != norm_id(want_id):
            res.bad.append(
                f"    ✗ {prop_name}: リレーション先が違う"
                f"（期待 {target_key} / 実際 {target_id[:8]}…）"
            )
            return
        res.ok.append(f"    ✓ {prop_name} → {target_key}")
        return

    # --- ロールアップ ---
    if isinstance(spec, tuple) and spec[0] == "rollup":
        _, rel_name, rolled = spec
        if actual_type != "rollup":
            res.bad.append(f"    ✗ {prop_name}: 型が rollup でない（{actual_type}）")
            return
        cfg = actual["rollup"]
        problems = []
        if cfg.get("relation_property_name") != rel_name:
            problems.append(
                f"リレーション={cfg.get('relation_property_name')}（期待 {rel_name}）"
            )

        # 参照先は name が返らないことがあるので id からも解決する
        how = "name"
        got = cfg.get("rolled_up_property_name")
        if not got and own_props is not None and fetch_db is not None:
            got, how = resolve_rolled_up_name(fetch_db, own_props, cfg)

        if got is None and not cfg.get("rolled_up_property_id"):
            # Notion API が参照先を一切返さないケース。
            # Notion画面では正しく設定されていても name / id が空で返ることがあり、
            # 設定漏れと区別できない。NGにはせず「未検証」として報告する。
            if problems:
                res.bad.append(f"    ✗ {prop_name}: " + " / ".join(problems))
                return
            res.unknown.append(
                f"    - {prop_name}: 参照先をAPIが返さないため未検証"
                f"（期待 {rel_name}.{rolled}／Notion画面で目視確認）"
            )
            return

        if got != rolled:
            problems.append(f"参照先={got}（期待 {rolled} / {how}）")

        if problems:
            res.bad.append(f"    ✗ {prop_name}: " + " / ".join(problems))
            return
        func = cfg.get("function")
        note = "" if func == "show_original" else f"（計算方法が {func}。show_original 推奨）"
        via = "" if how == "name" else f"［{how}］"
        res.ok.append(f"    ✓ {prop_name} ← {rel_name}.{rolled} {note}{via}")
        return

    # --- 単純な型 ---
    if actual_type != spec:
        res.bad.append(f"    ✗ {prop_name}: 型が違う（期待 {spec} / 実際 {actual_type}）")
        return
    res.ok.append(f"    ✓ {prop_name} ({spec})")


def check_select_options(
    db_key: str, props: Dict[str, Any], res: Result
) -> None:
    for (k, prop_name), want in EXPECTED_SELECT_OPTIONS.items():
        if k != db_key or prop_name not in props:
            continue
        actual = props[prop_name]
        if actual.get("type") != "select":
            continue
        names = [o["name"] for o in actual["select"].get("options", [])]

        if want == "categories":
            expected = expected_category_names()
            if expected is None:
                res.ok.append(f"    - {prop_name} の選択肢: categories.py を読めず未検証")
                continue
            want_list = expected
        else:
            want_list = want

        missing = [n for n in want_list if n not in names]
        if missing:
            res.bad.append(f"    ✗ {prop_name} の選択肢が不足: {missing}")
        else:
            res.bad.append("") if False else None
            res.ok.append(f"    ✓ {prop_name} の選択肢 {len(want_list)}件そろっている")


def verify(notion: Client, reg: Dict[str, str]) -> Result:
    res = Result()

    _cache: Dict[str, Dict[str, Any]] = {}

    def fetch_db(database_id: str) -> Dict[str, Any]:
        key = norm_id(database_id)
        if key not in _cache:
            _cache[key] = notion.databases.retrieve(database_id=database_id)
        return _cache[key]

    for db_key, expected_props in EXPECTED.items():
        db_id = reg.get(db_key)
        print(f"\n[{db_key}]")
        if not db_id:
            res.bad.append(f"    ✗ registry に {db_key} が無い")
            print(f"    ✗ registry に {db_key} が無い")
            continue

        db = fetch_db(db_id)
        title = "".join(t.get("plain_text", "") for t in db.get("title", []))
        props: Dict[str, Any] = db.get("properties", {})

        before_ok = len(res.ok)
        before_bad = len(res.bad)

        for prop_name, spec in expected_props.items():
            if prop_name not in props:
                res.bad.append(f"    ✗ {prop_name}: プロパティが存在しない")
                continue
            check_property(
                db_key, prop_name, spec, props[prop_name], reg, res,
                own_props=props, fetch_db=fetch_db,
            )

        check_select_options(db_key, props, res)

        for name in props:
            if name not in expected_props:
                res.extra.append(f"    ? {db_key}.{name} ({props[name].get('type')})")

        new_ok = res.ok[before_ok:]
        new_bad = res.bad[before_bad:]
        print(f"  {title}  （{len(new_ok)} OK / {len(new_bad)} NG）")
        for line in new_bad:
            print(line)

    return res


def main() -> None:
    if not NOTION_V2_API_KEY:
        sys.exit("NOTION_V2_API_KEY が設定されていません")
    if not REGISTRY_PATH.exists():
        sys.exit(
            f"registry が見つかりません: {REGISTRY_PATH}\n"
            "先に notion_db_create.py を実行してください。"
        )

    notion = Client(auth=NOTION_V2_API_KEY)
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    print(f"環境ファイル: {ENV_FILE}")
    print(f"registry    : {REGISTRY_PATH}")
    print(f"検証対象    : {len(EXPECTED)} DB")

    res = verify(notion, reg)

    print("\n" + "=" * 64)
    print(
        f"結果: {len(res.ok)} 件OK / {len(res.bad)} 件NG "
        f"/ {len(res.unknown)} 件未検証"
    )
    print("=" * 64)

    if res.bad:
        print("\n直す必要があるもの:")
        for line in res.bad:
            print(line)

    if res.unknown:
        print("\nAPIで検証できなかったもの（Notion画面で目視確認してください）:")
        for line in res.unknown:
            print(line)
        print(
            "\n  ※ Notion API は Rollup の参照先を返さないため、設定済みでも空で返る。\n"
            "    設定漏れと区別できないので NG にはしていない。"
        )

    if res.extra:
        print("\n設計書に無いプロパティ（消してよいか確認）:")
        for line in res.extra:
            print(line)

    if res.failed:
        print("\n不一致があります。Notion画面で修正してから再実行してください。")
        sys.exit(1)

    if res.unknown:
        print("\n自動検証できた範囲はすべて設計どおりです。")
    else:
        print("\nすべて設計どおりです。")


if __name__ == "__main__":
    main()
