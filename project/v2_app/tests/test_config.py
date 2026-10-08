"""config.py のテスト。設定が揃っているかの確認も兼ねる。"""

from __future__ import annotations

from v2_app.core import config
from v2_app.tests.harness import Suite

suite = Suite("config")


@suite.case("セッションのTTLは3日")
def _() -> None:
    assert config.SESSION_TTL_SECONDS == 60 * 60 * 24 * 3


@suite.case("REQUIRED は Notion の APIキー + DB 10個")
def _() -> None:
    assert len(config.REQUIRED) == 11, config.REQUIRED
    assert len(set(config.REQUIRED)) == 11


@suite.case("必須の環境変数が全部入っている")
def _() -> None:
    missing = config.missing_required()
    assert not missing, "足りない: " + ", ".join(missing)


@suite.case("assert_configured が通る")
def _() -> None:
    config.assert_configured()


@suite.case("DB_* の定数が10個とも空でない")
def _() -> None:
    names = [
        "DB_SCHOOL",
        "DB_USER",
        "DB_SUBJECT",
        "DB_SCHOOL_MEMBER",
        "DB_LESSON_STUDY",
        "DB_LESSON_STUDY_REFLECTION",
        "DB_DAILY_LEARNING",
        "DB_PRACTICE_EXAMPLE",
        "DB_RESEARCH_QUESTION",
        "DB_TEACHER_MONTHLY_STATS",
    ]
    empty = [n for n in names if not getattr(config, n)]
    assert not empty, "空: " + ", ".join(empty)


@suite.case("10個のDB IDは全部ちがう（env のコピペミス検出）")
def _() -> None:
    ids = [
        config.DB_SCHOOL,
        config.DB_USER,
        config.DB_SUBJECT,
        config.DB_SCHOOL_MEMBER,
        config.DB_LESSON_STUDY,
        config.DB_LESSON_STUDY_REFLECTION,
        config.DB_DAILY_LEARNING,
        config.DB_PRACTICE_EXAMPLE,
        config.DB_RESEARCH_QUESTION,
        config.DB_TEACHER_MONTHLY_STATS,
    ]
    assert len(set(ids)) == 10, "重複している ID がある"


@suite.case("使うモデル名が決まっている")
def _() -> None:
    assert config.MODEL_EXTRACT
    assert config.MODEL_ASK
