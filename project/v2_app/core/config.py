"""V2用の設定。環境変数の読み込みをここに集約する。

実行は Docker 前提。環境変数は compose の env_file（env/v2.local.env）から
コンテナの環境変数として注入されるので、このモジュールは os.getenv で読むだけ。
.env ファイルを自分で読み込むことはしない。

  docker compose -f docker/v2.local.yml up -d
  docker compose -f docker/v2.local.yml exec app python -m ...

V1 の project/core/config.py とは独立。
V1のキー（NOTION_API_KEY など）は参照しない。
"""
from __future__ import annotations

import os
from pathlib import Path

# ファイルパスの基準。.runtime などを参照するときに使う
PROJECT_DIR = Path(__file__).resolve().parents[2]   # /app/project
REPO_ROOT = PROJECT_DIR.parent                      # /app
RUNTIME_DIR = REPO_ROOT / ".runtime"


def _get(name: str, default: str = "") -> str:
    return os.getenv(name) or default


# --- Redis ---
REDIS_URL = _get("REDIS_URL", "redis://redis:6379/0")

# 入力途中データの寿命（3日）
SESSION_TTL_SECONDS = 60 * 60 * 24 * 3

# --- Notion ---
NOTION_API_KEY = _get("NOTION_V2_API_KEY")

ROOT_PAGE_ID = _get("NOTION_V2_ROOT_PAGE_ID")
MYPAGE_ROOT_ID = _get("NOTION_V2_MYPAGE_ROOT_ID")
SCHOOLPAGE_ROOT_ID = _get("NOTION_V2_SCHOOLPAGE_ROOT_ID")

# データベースID
DB_SCHOOL = _get("NOTION_V2_SCHOOL_DB_ID")
DB_USER = _get("NOTION_V2_USER_DB_ID")
DB_SUBJECT = _get("NOTION_V2_SUBJECT_DB_ID")
DB_SCHOOL_MEMBER = _get("NOTION_V2_SCHOOL_MEMBER_DB_ID")
DB_LESSON_STUDY = _get("NOTION_V2_LESSON_STUDY_DB_ID")
DB_LESSON_STUDY_REFLECTION = _get("NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID")
DB_DAILY_LEARNING = _get("NOTION_V2_DAILY_LEARNING_DB_ID")
DB_PRACTICE_EXAMPLE = _get("NOTION_V2_PRACTICE_EXAMPLE_DB_ID")
DB_RESEARCH_QUESTION = _get("NOTION_V2_RESEARCH_QUESTION_DB_ID")
DB_TEACHER_MONTHLY_STATS = _get("NOTION_V2_TEACHER_MONTHLY_STATS_DB_ID")

# --- Telegram（フェーズ3）---
TELEGRAM_BOT_TOKEN = _get("V2_TELEGRAM_BOT_TOKEN")
TELEGRAM_SECRET_TOKEN = _get("V2_TELEGRAM_SECRET_TOKEN")

# --- LLM（プロバイダ未選定 → TODO B-1）---
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_LLM_MODEL = _get("OPENAI_LLM_MODEL", "gpt-4o-mini")

# 用途別に分けられるようにする。未設定なら OPENAI_LLM_MODEL を使う
MODEL_EXTRACT = _get("V2_MODEL_EXTRACT") or OPENAI_LLM_MODEL   # 抽出・分類（英語）
MODEL_ASK = _get("V2_MODEL_ASK") or OPENAI_LLM_MODEL           # 問いかけ（クメール語）

# --- R2（メディア保存）---
R2_ACCOUNT_ID = _get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = _get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = _get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = _get("R2_BUCKET_NAME")
R2_FOLDER = _get("R2_FOLDER")
R2_PUBLIC_URL_BASE = _get("R2_PUBLIC_URL_BASE")

# --- Slack（Bot Token方式。2026-10-09決定）---
SLACK_BOT_TOKEN = _get("V2_SLACK_BOT_TOKEN")
SLACK_DEFAULT_CHANNEL = _get("V2_SLACK_DEFAULT_CHANNEL")

# 学校ごとにチャンネルを分ける場合のマップ。空なら既定チャンネルだけ使う
# 例: {"Hun Sen High School": "#impact-hunsen"}
try:
    SLACK_CHANNEL_MAP: dict = json.loads(_get("V2_SLACK_CHANNEL_MAP") or "{}")
except json.JSONDecodeError:
    SLACK_CHANNEL_MAP = {}


# 起動時に必ず揃っていてほしいもの
REQUIRED = (
    "NOTION_V2_API_KEY",
    "NOTION_V2_SCHOOL_DB_ID",
    "NOTION_V2_USER_DB_ID",
    "NOTION_V2_SUBJECT_DB_ID",
    "NOTION_V2_SCHOOL_MEMBER_DB_ID",
    "NOTION_V2_LESSON_STUDY_DB_ID",
    "NOTION_V2_LESSON_STUDY_REFLECTION_DB_ID",
    "NOTION_V2_DAILY_LEARNING_DB_ID",
    "NOTION_V2_PRACTICE_EXAMPLE_DB_ID",
    "NOTION_V2_RESEARCH_QUESTION_DB_ID",
    "NOTION_V2_TEACHER_MONTHLY_STATS_DB_ID",
)


def missing_required() -> list[str]:
    """足りない設定の名前を返す。"""
    return [name for name in REQUIRED if not os.getenv(name)]


def assert_configured() -> None:
    """起動時に呼ぶ。足りなければ原因が分かる形で落とす。

    _get() は空文字を返すだけなので、設定漏れがあっても
    Notion API が unauthorized を返すまで気づけない。
    起動時にここで落としたほうが原因が一目で分かる。
    """
    missing = missing_required()
    if not missing:
        return
    raise RuntimeError(
        "環境変数が足りません:\n  " + "\n  ".join(missing) + "\n\n"
        "Docker 経由で動かしていますか。"
        "compose の env_file（env/v2.local.env）から注入される前提です。\n"
        "  docker compose -f docker/v2.local.yml up -d\n"
        "  docker compose -f docker/v2.local.yml exec app python -m ..."
    )
