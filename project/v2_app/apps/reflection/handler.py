"""日々の振り返りの入口。会話ループは apps/base.py が持つ。"""

from __future__ import annotations

from typing import Any, Dict

from v2_app.apps import base
from v2_app.apps.reflection.schema import DB_ID, FIELDS
from v2_app.core import session, summarize
from v2_app.router.dispatcher import Incoming

ROUTE = "reflection"


def slack_head(user: Dict[str, Any], filled: Dict[str, Any]) -> str:
    """Slackの1行目。**何のレコードかを出す**（2026-10-13 ユーザー要望）。

    「has put the record」だけだと、振り返りなのか授業研究の
    コメントなのかがチャンネルで見分けられない。
    """
    return f"{user.get('name', 'A teacher')} has put a Daily Reflection"


async def before_save(inc: Incoming, user: Dict[str, Any]) -> None:
    """保存の直前に教科を抽出する。

    ⚠️ 対話中は聞かない（先生の手間を増やさない）。
    発話をそのまま入れた note から、保存の直前に1回だけ判定する。

    失敗しても空のまま進む。保存は止めない。
    """
    filled = (session.get_session(ROUTE, inc.telegram_id) or {}).get("filled", {})
    subject = await summarize.pick_subject(filled.get("note") or "")

    if subject:
        session.update_filled(ROUTE, inc.telegram_id, {"subject": subject})


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
        # ⚠️ 抽出を通さない。毎回 LLM が note を書き直すので、Add more を
        # 繰り返すと最後の書き直しだけが残る（2026-10-17 先方から指摘）
        use_llm=False,
        # 発話をそのまま note に足していく
        accumulate="note",
        # 保存の直前に教科を抜く
        before_save=before_save,
    )
