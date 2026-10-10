"""授業研究コメントの入口。

他のモードと違う点が2つ:
  ① 会話の前に「どの授業研究か」を一覧から選ばせる
  ② 保存の直前に8分類を当てる（core/categorize.py）
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict

from v2_app.apps import base
from v2_app.apps.lesson_study import repo
from v2_app.apps.lesson_study.schema import DB_ID, FIELDS
from v2_app.core import categorize, session, telegram
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

ROUTE = "lesson_study"
PICK = "ls:"

TEXTS: Dict[str, Dict[str, str]] = {
    "pick": {"en": "Which lesson study is this about?", "km": "តើនេះជាការសិក្សាបទបង្រៀនមួយណា?"},
    "none_open": {
        "en": "There is no open lesson study right now. Please ask the staff.",
        "km": "ឥឡូវនេះគ្មានការសិក្សាបទបង្រៀនបើកចំហទេ។ សូមសួរបុគ្គលិក។",
    },
}


def t(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en}\n{km}" if km else en


async def _show_list(inc: Incoming, user: Dict[str, Any]) -> None:
    studies = await repo.open_lesson_studies(user.get("school_id") or None)

    if not studies:
        await telegram.send_message(inc.chat_id, t("none_open"))
        session.clear_session(ROUTE, inc.telegram_id)
        return

    rows = []
    for page_id, name, date in studies:
        label = f"{name} ({date})" if date else name
        # callback_data は64バイトまで。"ls:" + page_id = 39バイト
        rows.append([(label, f"{PICK}{page_id}")])

    await telegram.send_message(
        inc.chat_id, t("pick"), reply_markup=telegram.inline_keyboard(rows)
    )


async def before_save(inc: Incoming, user: Dict[str, Any]) -> None:
    """保存の直前に8分類を当てる。"""
    filled = (session.get_session(ROUTE, inc.telegram_id) or {}).get("filled", {})

    label = await categorize.categorize(
        filled.get("comment") or "",
        text_en=filled.get("translated_en") or "",
    )
    if label:
        session.update_filled(ROUTE, inc.telegram_id, {"category": label})


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    sess = session.get_session(ROUTE, inc.telegram_id)
    if sess is None:
        # base が「/start からやり直してください」を出す
        await base.handle(inc, user, route=ROUTE, fields=FIELDS, db_id=DB_ID)
        return

    # --- まだ授業研究が選ばれていない ---
    if not sess.get("filled", {}).get("lesson_study"):
        if inc.is_callback and inc.text.startswith(PICK):
            page_id = inc.text[len(PICK) :]
            session.update_filled(ROUTE, inc.telegram_id, {"lesson_study": page_id})

            # 押したボタンを消す
            if inc.message_id:
                await telegram.edit_message_text(
                    inc.chat_id, inc.message_id, t("pick")
                )

            # 最初の質問に進む。callback のままだと base が
            # 保存ボタンの処理と誤認するので、空のテキストに変える
            await base.handle(
                dataclasses.replace(
                    inc, kind="text", text="", callback_id=None, file_id=None
                ),
                user,
                route=ROUTE,
                fields=FIELDS,
                db_id=DB_ID,
                before_save=before_save,
            )
            return

        await _show_list(inc, user)
        return

    # --- 選び終わっている。通常の会話ループ ---
    await base.handle(
        inc,
        user,
        route=ROUTE,
        fields=FIELDS,
        db_id=DB_ID,
        before_save=before_save,
    )
