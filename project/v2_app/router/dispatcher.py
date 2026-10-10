from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from v2_app.core import session, telegram, user_repo

log = logging.getLogger("impactdb.v2")


@dataclass
class Incoming:
    """Telegram の update を扱いやすい形に直したもの。

    handler がこれだけを見れば済むようにする。
    Telegram の生の構造（message / callback_query の分岐、
    photo が配列、caption が text の代わり）をここで吸収する。
    """

    update_id: int
    telegram_id: int
    chat_id: int
    kind: str              # text / voice / photo / video / document / callback
    text: str = ""         # 本文・caption・callback_data のどれか
    message_id: Optional[int] = None
    callback_id: Optional[str] = None
    file_id: Optional[str] = None
    mime_type: str = ""
    user_name: str = ""
    username: str = ""
    lang_code: str = ""    # Telegram が教えてくる言語。'km' / 'en' など
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_callback(self) -> bool:
        return self.kind == "callback"

    @property
    def has_media(self) -> bool:
        return self.file_id is not None


def _person(from_user: Dict[str, Any]) -> Dict[str, str]:
    name = " ".join(
        p for p in (from_user.get("first_name"), from_user.get("last_name")) if p
    )
    return {
        "user_name": name.strip(),
        "username": from_user.get("username") or "",
        "lang_code": from_user.get("language_code") or "",
    }


def parse(update: Dict[str, Any]) -> Optional[Incoming]:
    """update → Incoming。扱えないものは None。"""
    update_id = update.get("update_id", 0)

    # ボタンが押された場合
    cq = update.get("callback_query")
    if cq:
        msg = cq.get("message") or {}
        return Incoming(
            update_id=update_id,
            telegram_id=cq["from"]["id"],
            chat_id=(msg.get("chat") or {}).get("id") or cq["from"]["id"],
            kind="callback",
            text=cq.get("data") or "",
            message_id=msg.get("message_id"),
            callback_id=cq["id"],
            raw=update,
            **_person(cq["from"]),
        )

    msg = update.get("message") or update.get("edited_message")
    if not msg or "from" not in msg:
        return None

    base = dict(
        update_id=update_id,
        telegram_id=msg["from"]["id"],
        chat_id=msg["chat"]["id"],
        message_id=msg.get("message_id"),
        raw=update,
        **_person(msg["from"]),
    )

    if msg.get("voice"):
        v = msg["voice"]
        return Incoming(kind="voice", file_id=v["file_id"],
                        mime_type=v.get("mime_type") or "audio/ogg", **base)

    if msg.get("audio"):
        a = msg["audio"]
        return Incoming(kind="voice", file_id=a["file_id"],
                        mime_type=a.get("mime_type") or "audio/mpeg", **base)

    if msg.get("photo"):
        # photo は解像度ごとの配列。最後が一番大きい
        p = msg["photo"][-1]
        return Incoming(kind="photo", file_id=p["file_id"],
                        mime_type="image/jpeg",
                        text=msg.get("caption") or "", **base)

    if msg.get("video") or msg.get("video_note"):
        v = msg.get("video") or msg["video_note"]
        return Incoming(kind="video", file_id=v["file_id"],
                        mime_type=v.get("mime_type") or "video/mp4",
                        text=msg.get("caption") or "", **base)

    if msg.get("document"):
        d = msg["document"]
        return Incoming(kind="document", file_id=d["file_id"],
                        mime_type=d.get("mime_type") or "",
                        text=msg.get("caption") or "", **base)

    if msg.get("text"):
        return Incoming(kind="text", text=msg["text"], **base)

    # ステッカー・位置情報・入退室の通知など
    return None


async def handle_update(update: Dict[str, Any]) -> None:
    """振り分けの入口。main.py が裏で呼ぶ。"""
    inc = parse(update)
    if inc is None:
        log.info("扱えない update update_id=%s", update.get("update_id"))
        return

    # ⚠️ ボタンのくるくるを最初に止める。処理が長いと
    # 先生の画面が固まって見えて、連打の原因になる
    if inc.is_callback and inc.callback_id:
        await telegram.answer_callback_query(inc.callback_id)

    # Telegram が教えてくる言語を初回だけ控えておく
    if inc.lang_code and not session.get_lang(inc.telegram_id):
        session.set_lang(inc.telegram_id, inc.lang_code[:2])

    user = await user_repo.get_or_create_user(
        inc.telegram_id, inc.user_name, inc.username
    )

    # 遅延 import。router → apps → core の向きだけにして循環を避ける
    from v2_app.apps import registry
    from v2_app.router import menu

    # コマンドは route より優先する。どこで詰まっても抜け出せるように
    if inc.kind == "text" and inc.text.startswith("/"):
        await menu.handle_command(inc, user)
        return

    # 学校が決まっていない先生は、まず所属を選んでもらう
    if not user.get("school_id"):
        await menu.onboard(inc, user)
        return

    route = session.get_route(inc.telegram_id)
    if not route:
        await menu.show(inc, user)
        return

    handler = registry.get_handler(route)
    if handler is None:
        log.warning("未知の route=%s telegram_id=%s", route, inc.telegram_id)
        session.clear_route(inc.telegram_id)
        await menu.show(inc, user)
        return

    await handler(inc, user)
