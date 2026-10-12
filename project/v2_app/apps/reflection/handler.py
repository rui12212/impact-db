"""日々の振り返りの入口。会話ループは apps/base.py が持つ。"""

from __future__ import annotations

from typing import Any, Dict

from v2_app.apps import base
from v2_app.apps.reflection.schema import DB_ID, FIELDS
from v2_app.router.dispatcher import Incoming

ROUTE = "reflection"


def slack_head(user: Dict[str, Any], filled: Dict[str, Any]) -> str:
    """Slackの1行目。**何のレコードかを出す**（2026-10-13 ユーザー要望）。

    「has put the record」だけだと、振り返りなのか授業研究の
    コメントなのかがチャンネルで見分けられない。
    """
    return f"{user.get('name', 'A teacher')} has put a Daily Reflection"


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    await base.handle(
        inc,
        user,
        route=ROUTE,
        fields=FIELDS,
        db_id=DB_ID,
        # Slack に要約を流す（→ v2-slack.md）
        post_to_slack=True,
        slack_head=slack_head,
    )
