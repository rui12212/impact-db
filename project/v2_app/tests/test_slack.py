"""slack.py の投稿先の決め方のテスト。

⚠️ **「どこにも送らない」が正常系**なので、そこを固定する。
既定チャンネルへ逃がす実装に戻すと、Slackに流さないと決めた
学校の記録が流れ続ける（2026-10-25決定）。
"""

from __future__ import annotations

from contextlib import contextmanager

from v2_app.core import slack
from v2_app.tests.harness import Suite

suite = Suite("slack")

# ハイフン付き（APIの relation の形）とハイフン無し（NotionのURLの形）
HYPHEN = "4002e6dc-c84a-81de-a8d7-c848876b287a"
PLAIN = "4002e6dcc84a81dea8d7c848876b287a"
CHANNEL = "C09ABCD1234"


@contextmanager
def mapped(raw: dict):
    """env のマップを入れ替える。

    _CHANNEL_MAP は import 時に1回作るので、env を触っても効かない。
    正規化込みで作り直す
    """
    before = slack._CHANNEL_MAP
    slack._CHANNEL_MAP = {slack._norm(k): v for k, v in raw.items()}
    try:
        yield
    finally:
        slack._CHANNEL_MAP = before


@suite.case("ハイフン付きのIDで引ける")
def _() -> None:
    with mapped({PLAIN: CHANNEL}):
        assert slack.channel_for(HYPHEN) == CHANNEL


@suite.case("ハイフン無しのIDでも同じチャンネルになる")
def _() -> None:
    """⚠️ envに貼るIDはURL由来でハイフンが無く、
    user["school_id"] はハイフン付き。**どちらでも一致しないと届かない**
    """
    with mapped({HYPHEN: CHANNEL}):
        assert slack.channel_for(PLAIN) == CHANNEL


@suite.case("登録の無い学校はどこにも送らない")
def _() -> None:
    with mapped({PLAIN: CHANNEL}):
        assert slack.channel_for("ffffffffffffffffffffffffffffffff") == ""


@suite.case("学校IDが空ならどこにも送らない")
def _() -> None:
    with mapped({PLAIN: CHANNEL}):
        assert slack.channel_for("") == ""


@suite.case("マップが空ならどこにも送らない")
def _() -> None:
    with mapped({}):
        assert slack.channel_for(HYPHEN) == ""


@suite.case("学校名では引けない（IDに移行済みの確認）")
def _() -> None:
    with mapped({"Labo School": CHANNEL}):
        assert slack.channel_for("Labo School") == CHANNEL
        # 名前をキーに入れても、先生から来るのはIDなので一致しない
        assert slack.channel_for(HYPHEN) == ""
