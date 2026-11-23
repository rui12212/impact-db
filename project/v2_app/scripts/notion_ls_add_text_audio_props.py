"""Lesson Study Reflection に4つのプロパティを足す。

  # 何が足されるか見るだけ（Notionに書かない）
  docker compose -f docker/v2.local.yml exec \
      -e V2_ENV_FILE=env/v2.dev.env app \
      python -m v2_app.scripts.notion_ls_add_text_audio_props --dry-run

  # 実行
  docker compose -f docker/v2.local.yml exec \
      -e V2_ENV_FILE=env/v2.dev.env app \
      python -m v2_app.scripts.notion_ls_add_text_audio_props

なぜ必要か（2026-10-26決定）:
  → modify/2026-10-26-lesson-study-text-audio-restructure.md

  いまは**言語で**プロパティを分けている（原文=STT_Km / 英訳=Translated_En）。
  これを**入力手段で**分ける形に変える。

    Text_org       打ち込み＋caption の原文
    Audio_stt_org  音声の文字起こし原文
    Comment_org    上2つの結合（先生の言語。Summary / Keywords の元）
    Comment_eng    その英訳（カテゴライズの入力）

⚠️ **リネームではなく「追加」にする。** Notion は存在しないプロパティ名に
   400 を返し、**ページ作成そのものが失敗する**（記録が1件も残らない）。
   リネームするとコードのデプロイまでの間、保存が全部落ちる。
   足すだけなら使われないプロパティが増えるだけなので**窓がゼロ**。

⚠️ **本番と dev の両方で流す。** Notion が別なので2回必要。
   名前はこのファイルに1箇所しか書いていないので、**取り違えが起きない**
   （手でUIに8回打つと `Comment_Org` と `Comment_org` を取り違える）。

⚠️ 旧プロパティ（Comment / STT_Km / Translated_En）は**消さない。**
   既存レコードの移行と、ロールバックの余地を残すため。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from dotenv import load_dotenv

# ⚠️ **V2_ENV_FILE を必ず要求する。** config から読むだけだと、コンテナに
# 注入された環境変数を使ってしまい、dev を触ったつもりで本番を直す
# （あるいは逆）という事故になる。override=True が必須
_ENV_FILE = os.getenv("V2_ENV_FILE", "")
if not _ENV_FILE:
    raise SystemExit(
        "V2_ENV_FILE を指定してください（例: -e V2_ENV_FILE=env/v2.dev.env）。\n"
        "どちらの環境を触るかを明示させるため、既定値は持たせていません。"
    )
_path = _ENV_FILE if os.path.isabs(_ENV_FILE) else f"/app/{_ENV_FILE}"
if not os.path.exists(_path):
    raise SystemExit(f"環境ファイルが見つかりません: {_path}")
load_dotenv(_path, override=True)

log = logging.getLogger("impactdb.v2")

# 足すプロパティ。**ここが名前の単一の正**
NEW_PROPS = {
    "Text_org": {"rich_text": {}},
    "Audio_stt_org": {"rich_text": {}},
    "Comment_org": {"rich_text": {}},
    "Comment_eng": {"rich_text": {}},
}


def _title_of(db: dict) -> str:
    items = db.get("title", [])
    return "".join(i.get("plain_text", "") for i in items) or "(無題)"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="書かずに一覧だけ")
    args = parser.parse_args()

    # ⚠️ import はここで。load_dotenv より先に config を読ませない
    from v2_app.core.notion_client import get_notion

    db_id = os.getenv("NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID")
    if not db_id:
        print("NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID が未設定")
        return 1

    notion = get_notion()
    db = await notion.databases.retrieve(database_id=db_id)
    existing = db.get("properties", {})

    # --- どこを触るか見せる ---
    print()
    print("=" * 62)
    print(f"  env ファイル : {_ENV_FILE}")
    print(f"  データベース : {_title_of(db)}")
    print(f"  DB ID        : ...{db_id.replace('-', '')[-8:]}")
    print(f"  既存プロパティ: {len(existing)}個")
    print("=" * 62)
    print()

    todo = {}
    blocked = []
    for name, spec in NEW_PROPS.items():
        want = next(iter(spec))
        if name not in existing:
            print(f"  add    {name:16} {want}")
            todo[name] = spec
            continue

        got = existing[name].get("type", "")
        if got == want:
            print(f"  ok     {name:16} 既にある（型も一致）")
        else:
            # ⚠️ 手でUIに作っていて型が違う場合。**黙って上書きしない**
            print(f"  NG     {name:16} 既にあるが型が {got}（期待は {want}）")
            blocked.append(name)

    if blocked:
        print()
        print("中止しました。型が違うプロパティがあります:")
        for name in blocked:
            print(f"  {name}")
        print("Notion で型を直すか、名前を変えてから再実行してください。")
        return 1

    if not todo:
        print("\n足すものはありません（既に全部あります）")
        return 0

    print(f"\n{len(todo)}個を足します。既存のプロパティには触りません。")
    print("（databases.update の properties は**名前でマージ**する）")
    if args.dry_run:
        print("--dry-run なので実行しません")
        return 0

    answer = input("続けますか [y/N]: ").strip().lower()
    if answer != "y":
        print("中止しました")
        return 1

    try:
        await notion.databases.update(database_id=db_id, properties=todo)
    except Exception as e:
        print(f"\n失敗: {str(e)[:200]}")
        log.exception("プロパティの追加に失敗")
        return 1

    # --- 本当に入ったか読み直して確かめる ---
    after = (await notion.databases.retrieve(database_id=db_id)).get(
        "properties", {}
    )
    missing = [n for n in NEW_PROPS if n not in after]
    if missing:
        print(f"\n⚠️ 足せていないものがあります: {missing}")
        return 1

    print("\n足しました:")
    for name in NEW_PROPS:
        print(f"  {name:16} {after[name].get('type')}")
    print("\nこのあと:")
    print("  1. 既存レコードの移行（Comment / STT_Km から埋め直す）")
    print("  2. コード変更（schema.py / before_save / 翻訳プロンプト）")
    print("  3. もう一方の環境でもこのスクリプトを流す")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    raise SystemExit(asyncio.run(main()))
