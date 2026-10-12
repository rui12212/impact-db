"""設定。名前変更と転校。

他のモードと違い会話ではないので schema.py も base.py も使わない。
入力待ちの状態だけ session の filled に持たせる。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

from v2_app.core import session, telegram, user_repo
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

# 投げっぱなしのタスクの置き場。参照を持たないとGCに回収される
_background: Set[asyncio.Task] = set()

ROUTE = "settings"
DB_ID = ""
FIELDS: list = []

# callback_data の接頭辞
MENU_SCHOOL = "set:school"
MENU_NAME = "set:name"
MENU_DONE = "set:done"
PICK_SCHOOL = "setschool:"

TEXTS: Dict[str, Dict[str, str]] = {
    "menu": {"en": "What would you like to change?", "km": "តើអ្នកចង់ផ្លាស់ប្តូរអ្វី?"},
    "btn_school": {"en": "Change school", "km": "ផ្លាស់ប្តូរសាលា"},
    "btn_name": {"en": "Change name", "km": "ផ្លាស់ប្តូរឈ្មោះ"},
    "btn_done": {"en": "Done", "km": "រួចរាល់"},
    "ask_name": {"en": "What name should I use?", "km": "តើខ្ញុំគួរប្រើឈ្មោះអ្វី?"},
    "name_saved": {"en": "Your name has been updated.", "km": "ឈ្មោះរបស់អ្នកត្រូវបានធ្វើបច្ចុប្បន្នភាព។"},
    "ask_school": {"en": "Which school are you at now?", "km": "តើឥឡូវនេះអ្នកនៅសាលាណា?"},
    "school_saved": {"en": "Your school has been updated.", "km": "សាលារបស់អ្នកត្រូវបានធ្វើបច្ចុប្បន្នភាព។"},
    "no_schools": {
        "en": "No schools are registered yet. Please contact the staff.",
        "km": "មិនទាន់មានសាលាណាមួយត្រូវបានចុះឈ្មោះទេ។ សូមទាក់ទងបុគ្គលិក។",
    },
    "current": {"en": "Now:", "km": "បច្ចុប្បន្ន៖"},
    "done": {
        "en": "Saved successfully.",
        "km": "បានរក្សាទុកដោយជោគជ័យ។",
    },
    "same_school": {
        "en": "That is already your school.",
        "km": "នោះជាសាលារបស់អ្នករួចហើយ។",
    },
}


def t(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en}\n{km}" if km else en


def _btn(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en} / {km}" if km else en


def _refresh_mypage(user: Dict[str, Any]) -> None:
    """マイページ先頭の名前・学校名を裏で直す。

    **先生を待たせない。** Notionの書き換えは3〜4往復かかるので、
    Telegramには先に「保存しました」を返し、ここは投げっぱなしにする。

    夜間バッチを待たずに即時で反映するため（2026-10-13 ユーザー要望）。
    """
    page_id = user.get("notion_page_id")
    if not page_id:
        return

    async def job() -> None:
        from v2_app.scripts import notion_page_create

        await notion_page_create.refresh_header(page_id)

    task = asyncio.create_task(job())
    _background.add(task)
    task.add_done_callback(_background.discard)
    task.add_done_callback(_log_failure)


def _log_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        log.warning("マイページのヘッダー更新に失敗: %s", exc)


async def _show_menu(inc: Incoming, user: Dict[str, Any]) -> None:
    rows = [
        [(_btn("btn_name"), MENU_NAME)],
        [(_btn("btn_school"), MENU_SCHOOL)],
        [(_btn("btn_done"), MENU_DONE)],
    ]
    head = (
        f"{t('menu')}\n\n"
        f"{t('current')} {user.get('name', '')} / {user.get('school_name', '')}"
    )
    await telegram.send_message(
        inc.chat_id, head, reply_markup=telegram.inline_keyboard(rows)
    )


async def _show_schools(inc: Incoming, user: Dict[str, Any]) -> None:
    schools = await user_repo.list_schools()
    if not schools:
        await telegram.send_message(inc.chat_id, t("no_schools"))
        return

    rows = [[(name, f"{PICK_SCHOOL}{page_id}")] for page_id, name in schools if name]
    await telegram.send_message(
        inc.chat_id, t("ask_school"), reply_markup=telegram.inline_keyboard(rows)
    )


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    if session.get_session(ROUTE, inc.telegram_id) is None:
        session.new_session(ROUTE, inc.telegram_id, [])

    # --- ボタン ---
    if inc.is_callback:
        data = inc.text

        if data == MENU_NAME:
            session.set_pending(ROUTE, inc.telegram_id, "name")
            await telegram.send_message(inc.chat_id, t("ask_name"))
            return

        if data == MENU_SCHOOL:
            session.set_pending(ROUTE, inc.telegram_id, "")
            await _show_schools(inc, user)
            return

        if data.startswith(PICK_SCHOOL):
            page_id = data[len(PICK_SCHOOL) :]
            before = user.get("school_id", "")
            updated = await user_repo.set_school(inc.telegram_id, page_id)
            if inc.message_id:
                await telegram.edit_message_text(
                    inc.chat_id, inc.message_id, updated.get("school_name") or ""
                )
            # set_school は同じ学校なら何もせず返す。「変えました」と出さない
            changed = updated.get("school_id", "") != before
            await telegram.send_message(
                inc.chat_id, t("school_saved") if changed else t("same_school")
            )
            if changed:
                _refresh_mypage(updated)
            await _show_menu(inc, updated)
            return

        if data == MENU_DONE:
            session.clear_session(ROUTE, inc.telegram_id)
            # モード選択は出さない。設定を閉じたら終わり（2026-10-13 ユーザー要望）
            await telegram.send_message(inc.chat_id, t("done"))
            return

        return

    # --- 名前の入力を待っている ---
    if (
        session.get_pending(ROUTE, inc.telegram_id) == "name"
        and inc.kind == "text"
        and inc.text
    ):
        updated = await user_repo.rename(inc.telegram_id, inc.text.strip())
        session.set_pending(ROUTE, inc.telegram_id, "")
        await telegram.send_message(inc.chat_id, t("name_saved"))
        _refresh_mypage(updated)
        await _show_menu(inc, updated)
        return

    await _show_menu(inc, user)
