"""日々の振り返りの入口。会話ループは apps/base.py が持つ。"""

from __future__ import annotations

from typing import Any, Dict

from v2_app.apps import base
from v2_app.apps.reflection.schema import DB_ID, FIELDS
from v2_app.router.dispatcher import Incoming

ROUTE = "reflection"


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    await base.handle(
        inc,
        user,
        route=ROUTE,
        fields=FIELDS,
        db_id=DB_ID,
        # 振り返りだけ Slack に要約を流す（§3-4）
        post_to_slack=True,
    )
