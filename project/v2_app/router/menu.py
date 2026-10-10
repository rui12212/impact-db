from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from v2_app.core import session, telegram, user_repo
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

# 画面に出す文言。1通に英語とクメール語を並べる（2026-10-09決定）。
# km が空のものは英語だけ出る。現地から訳が届いたらここに書き足すだけで、
# menu.py も handler も触らなくて済む。
TEXTS: Dict[str, Dict[str, str]] = {
    "menu_prompt": {
        "en": "What would you like to record?",
        "km": "តើអ្នកចង់កត់ត្រាអ្វី?",
    },
    "ask_school": {
        "en": "Which school are you at?",
        "km": "តើអ្នកនៅសាលាណា?",
    },
    "ask_name": {
        "en": "What is your name?",
        "km": "តើអ្នកឈ្មោះអ្វី?",
    },
    "school_saved": {
        "en": "Thank you. Your school has been set.",
        "km": "អរគុណ។ សាលារបស់អ្នកត្រូវបានកំណត់។",
    },
    "cancelled": {
        "en": "Cancelled. Nothing was saved.",
        "km": "បានបោះបង់។ គ្មានអ្វីត្រូវបានរក្សាទុកទេ។",
    },
    "no_schools": {
        "en": "No schools are registered yet. Please contact the staff.",
        "km": "មិនទាន់មានសាលាណាមួយត្រូវបានចុះឈ្មោះទេ។ សូមទាក់ទងបុគ្គលិក។",
    },
    "help": {
        "en": "/start  choose what to record\n/cancel  discard what you are writing",
        "km": "/start ជ្រើសរើសអ្វីដែលត្រូវកត់ត្រា\n/cancel លុបអ្វីដែលអ្នកកំពុងសរសេរ",
    },
}

# route のキー と 表示名。キーは apps/registry.py の ROUTES と一致させる
MODES: List[Tuple[str, str, str]] = [
    ("reflection",        "Daily Reflection",  "ការឆ្លុះបញ្ចាំងប្រចាំថ្ងៃ"),
    ("practice",          "Practice Example",  "ឧទាហរណ៍នៃការអនុវត្ត"),
    ("lesson_study",      "Lesson Study",      "ការសិក្សាបទបង្រៀន"),
    ("research_question", "Research Question", "សំណួរស្រាវជ្រាវ"),
    ("settings",          "Settings",          "ការកំណត់"),
]


def t(key: str) -> str:
    """文言を1つ取る。英語とクメール語を改行で並べる。"""
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en}\n{km}" if km else en


def label(en: str, km: str) -> str:
    """ボタンの文字。英語 / クメール語 を1行に並べる。"""
    return f"{en} / {km}" if km else en


async def show(inc: Incoming, user: Dict[str, Any]) -> None:
    """モード選択を出す。route が無い時に dispatcher が呼ぶ。

    ボタンが押された場合（menu:xxx）はここでモードを開始する。
    route が無い状態で来る callback はメニューのものしかない。
    """
    if inc.is_callback and inc.text.startswith("menu:"):
        await _start_mode(inc, inc.text[len("menu:"):])
        return

    rows = [
        [(label(en, km), f"menu:{key}")] for key, en, km in MODES
    ]
    await telegram.send_message(
        inc.chat_id, t("menu_prompt"), reply_markup=telegram.inline_keyboard(rows)
    )


async def _start_mode(inc: Incoming, route: str) -> None:
    """選ばれたモードを開始する。"""
    from v2_app.apps import registry

    entry = registry.ROUTES.get(route)
    if entry is None:
        log.warning("未知のモード route=%s", route)
        return

    # 押したボタンを消す。あとから押し直せないように
    if inc.message_id:
        await telegram.edit_message_text(
            inc.chat_id, inc.message_id, _chosen_label(route)
        )

    session.new_session(route, inc.telegram_id, entry["fields"])
    handler = entry["handler"]
    await handler(inc, await user_repo.get_or_create_user(inc.telegram_id))


def _chosen_label(route: str) -> str:
    for key, en, km in MODES:
        if key == route:
            return label(en, km)
    return route


async def handle_command(inc: Incoming, user: Dict[str, Any]) -> None:
    """/start /cancel /help。route より優先して処理される。

    対話の途中で詰まっても、ここから必ず抜け出せるようにする。
    """
    cmd = inc.text.split()[0].split("@")[0].lower()

    if cmd in ("/start", "/menu"):
        route = session.get_route(inc.telegram_id)
        if route:
            session.clear_session(route, inc.telegram_id)
        await show(inc, user)
        return

    if cmd == "/cancel":
        route = session.get_route(inc.telegram_id)
        if route:
            session.clear_session(route, inc.telegram_id)
        await telegram.send_message(inc.chat_id, t("cancelled"))
        await show(inc, user)
        return

    # /help と知らないコマンド
    await telegram.send_message(inc.chat_id, t("help"))


async def onboard(inc: Incoming, user: Dict[str, Any]) -> None:
    """所属が決まっていない先生に学校を選ばせる。

    名前は Telegram の first_name / last_name から取れているので聞かない。
    変えたい先生は Settings から直せる。
    """
    if inc.is_callback and inc.text.startswith("school:"):
        school_id = inc.text[len("school:"):]
        updated = await user_repo.set_school(inc.telegram_id, school_id)
        if inc.message_id:
            await telegram.edit_message_text(
                inc.chat_id, inc.message_id, updated.get("school_name") or ""
            )
        await telegram.send_message(inc.chat_id, t("school_saved"))
        await show(inc, updated)
        return

    schools = await user_repo.list_schools()
    if not schools:
        await telegram.send_message(inc.chat_id, t("no_schools"))
        return

    rows = [[(name, f"school:{page_id}")] for page_id, name in schools if name]
    await telegram.send_message(
        inc.chat_id, t("ask_school"), reply_markup=telegram.inline_keyboard(rows)
    )
