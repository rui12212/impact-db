"""session.py のテスト。Redis に実際に書く（テスト用IDだけ使う）。"""

from __future__ import annotations

from v2_app.core import session
from v2_app.core.redis_client import get_redis
from v2_app.tests.fixtures import DAILY_FIELDS, TEST_APP, TEST_TELEGRAM_ID
from v2_app.tests.harness import Suite

suite = Suite("session (Redis)")

UID = TEST_TELEGRAM_ID
APP = TEST_APP


def _reset() -> None:
    session.clear_session(APP, UID)
    session.clear_user(UID)


@suite.case("Redis に繋がる")
def _() -> None:
    assert get_redis().ping() is True


@suite.case("new_session は filled を全キー None で作り、route も書く")
def _() -> None:
    _reset()
    s = session.new_session(APP, UID, DAILY_FIELDS)
    assert set(s["filled"]) == {f["key"] for f in DAILY_FIELDS}
    assert all(v is None for v in s["filled"].values())
    assert s["ask_count"] == 0
    assert session.get_route(UID) == APP


@suite.case("get_session は保存した内容を読み戻せる")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    s = session.get_session(APP, UID)
    assert s is not None
    assert "started_at" in s


@suite.case("update_filled は filled を返す")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    filled = session.update_filled(APP, UID, {"note": "分数をやった"})
    assert filled is not None
    assert filled["note"] == "分数をやった"


@suite.case("update_filled は None を無視する（既存の値を消さない）")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    session.update_filled(APP, UID, {"note": "分数"})
    filled = session.update_filled(APP, UID, {"note": None, "subject": "算数"})
    assert filled["note"] == "分数"
    assert filled["subject"] == "算数"


@suite.case("update_filled は未知のキーを捨てる")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    filled = session.update_filled(APP, UID, {"note": "a", "unknown_key": "x"})
    assert "unknown_key" not in filled


@suite.case("update_filled: セッションが無ければ None")
def _() -> None:
    _reset()
    assert session.update_filled(APP, UID, {"note": "a"}) is None


@suite.case("bump_ask_count は 1 ずつ増え、保存される")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    assert session.bump_ask_count(APP, UID) == 1
    assert session.bump_ask_count(APP, UID) == 2
    assert session.get_session(APP, UID)["ask_count"] == 2


@suite.case("bump_ask_count: セッションが無ければ 0")
def _() -> None:
    _reset()
    assert session.bump_ask_count(APP, UID) == 0


@suite.case("history は追加した順に返る")
def _() -> None:
    _reset()
    session.append_history(APP, UID, "user", "こんにちは")
    session.append_history(APP, UID, "assistant", "今日はどうでしたか？")
    session.append_history(APP, UID, "user", "分数をやりました")
    h = session.get_history(APP, UID)
    assert [x["role"] for x in h] == ["user", "assistant", "user"]
    assert h[0]["content"] == "こんにちは"


@suite.case("get_history(last_n) は末尾から取る")
def _() -> None:
    _reset()
    for i in range(5):
        session.append_history(APP, UID, "user", str(i))
    h = session.get_history(APP, UID, last_n=2)
    assert [x["content"] for x in h] == ["3", "4"], h


@suite.case("get_history: 空なら空リスト")
def _() -> None:
    _reset()
    assert session.get_history(APP, UID) == []


@suite.case("clear_session は session/history/route を消す")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    session.append_history(APP, UID, "user", "a")
    session.clear_session(APP, UID)
    assert session.get_session(APP, UID) is None
    assert session.get_history(APP, UID) == []
    assert session.get_route(UID) is None


@suite.case("session / history / route には TTL が付く")
def _() -> None:
    _reset()
    session.new_session(APP, UID, DAILY_FIELDS)
    session.append_history(APP, UID, "user", "a")
    r = get_redis()
    for key in (
        f"{APP}:session:{UID}",
        f"{APP}:history:{UID}",
        f"route:{UID}",
    ):
        ttl = r.ttl(key)
        assert ttl > 0, f"{key} に TTL が無い: {ttl}"


@suite.case("user には TTL を付けない（永続）")
def _() -> None:
    _reset()
    session.set_user(UID, {"name": "Sok", "notion_page_id": "p1"})
    # -1 = キーはあるが期限なし
    assert get_redis().ttl(f"user:{UID}") == -1


@suite.case("get_user / set_user は往復する")
def _() -> None:
    _reset()
    session.set_user(UID, {"name": "Sok", "school_id": "s1"})
    u = session.get_user(UID)
    assert u["name"] == "Sok"
    assert u["school_id"] == "s1"


@suite.case("set_lang は既存の user を壊さない")
def _() -> None:
    _reset()
    session.set_user(UID, {"name": "Sok", "notion_page_id": "p1"})
    session.set_lang(UID, "km")
    u = session.get_user(UID)
    assert u["lang"] == "km"
    assert u["name"] == "Sok"


@suite.case("get_lang: user が無ければ None")
def _() -> None:
    _reset()
    assert session.get_lang(UID) is None


@suite.case("clear_session は user を消さない（所属情報は残す）")
def _() -> None:
    _reset()
    session.set_user(UID, {"name": "Sok"})
    session.new_session(APP, UID, DAILY_FIELDS)
    session.clear_session(APP, UID)
    assert session.get_user(UID) is not None
    _reset()


@suite.case("アプリが違えばセッションは独立している")
def _() -> None:
    _reset()
    other = TEST_APP + "_2"
    session.clear_session(other, UID)
    session.new_session(APP, UID, DAILY_FIELDS)
    session.update_filled(APP, UID, {"note": "A"})
    session.new_session(other, UID, DAILY_FIELDS)
    session.update_filled(other, UID, {"note": "B"})
    assert session.get_session(APP, UID)["filled"]["note"] == "A"
    assert session.get_session(other, UID)["filled"]["note"] == "B"
    # route は1つしかないので後から始めた方で上書きされる（= 1人1セッションの入口）
    assert session.get_route(UID) == other
    session.clear_session(other, UID)
    _reset()
