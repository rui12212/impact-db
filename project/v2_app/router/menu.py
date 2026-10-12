from __future__ import annotations

import asyncio
import dataclasses
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
        "en": "/new  start a new record\n/cancel  discard what you are writing",
        "km": "/new  ចាប់ផ្តើមកត់ត្រាថ្មី\n/cancel  លុបអ្វីដែលអ្នកកំពុងសរសេរ",
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


# まだ先生に見せないモード（2026-10-13）。
# ⚠️ MODES からは消さない。registry._SPECS との一致をテストで見ているので、
# 消すとテストが落ちる。それに「実装はあるが出さないだけ」という状態を
# コードに残しておきたい。戻す時はここから外すだけ
HIDDEN_MODES = {"practice"}


def visible_modes() -> List[Tuple[str, str, str]]:
    """モード選択に出すものだけ。"""
    return [m for m in MODES if m[0] not in HIDDEN_MODES]


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
        log.info("[5] show: モードが選ばれた %s", inc.text)
        await _start_mode(inc, inc.text[len("menu:"):])
        return

    # ⚠️ 所属が決まっていなければ学校選択に回す（2026-10-13修正）。
    #
    # dispatcher はコマンドを所属チェックより先に処理する（詰まった時に
    # /start で抜け出せるようにするため）。その結果、**新しい先生が
    # 最初に打つ /start が学校選択を飛ばしてモード選択に進んでしまう。**
    # 先生は必ず /start から始めるので、全員がこれを踏む。
    if not user.get("school_id"):
        log.info("[5] show: 所属なし -> onboard")
        await onboard(inc, user)
        return

    # 所属は決まっているのにマイページが無い先生を拾う（2026-10-13）。
    # 所属選択の時に作るのが本筋だが、
    #   ① その場で失敗した
    #   ② アドミンがNotionで直接 School Member を作った
    #   ③ マイページの仕組みより先にBotを使い始めた
    # の場合に、ここで作る。既にあれば何もしない（Redisのキャッシュを見るだけ）
    _ensure_mypage(inc, user)

    log.info("[5] show: モード選択を出す")
    rows = [
        [(label(en, km), f"menu:{key}")] for key, en, km in visible_modes()
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
    log.info("[6] new_session した route=%s", route)

    # ⚠️ ボタンのイベントをそのまま handler に渡してはいけない。
    # base.handle は callback を見ると「保存か追加か」を調べ、
    # どちらでもないので**黙って return する**。
    # その結果、モードを選んでも最初の質問が出ない（2026-10-13に実機で発生）。
    # 「本文が空のテキスト」に変換して渡す
    opening = dataclasses.replace(
        inc, kind="text", text="", callback_id=None, file_id=None
    )
    handler = entry["handler"]
    await handler(opening, await user_repo.get_or_create_user(inc.telegram_id))


NOW_ON_EN = "Now you are on"
NOW_ON_KM = "ឥឡូវនេះអ្នកនៅលើ"


def _chosen_label(route: str) -> str:
    """モードを選んだ後に、押したボタンを書き換える文。

    ただのモード名だと「選べたのか」が分かりにくいので
    「Now you are on 〜」にする（2026-10-13）。
    """
    for key, en, km in MODES:
        if key == route:
            if km:
                return f"{NOW_ON_EN} {en}\n{NOW_ON_KM} {km}"
            return f"{NOW_ON_EN} {en}"
    return route


async def handle_command(inc: Incoming, user: Dict[str, Any]) -> None:
    """/start /cancel /help。route より優先して処理される。

    対話の途中で詰まっても、ここから必ず抜け出せるようにする。
    """
    cmd = inc.text.split()[0].split("@")[0].lower()

    # ⚠️ /start も受ける。Telegramが初回に必ず表示するボタンなので、
    # 無効にすると新しい先生が入口を失う
    if cmd in ("/new", "/start", "/menu"):
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


# 裏で走らせたタスクの参照を持っておく。
# 持たないとガベージコレクタに回収されて途中で止まりうる
_background: set = set()


async def _build_mypage(telegram_id: int, user: Dict[str, Any]) -> None:
    """マイページを作る本体。裏で走る。

    ⚠️ 先生を待たせない（2026-10-13決定）。Notionへの呼び出しが
    15回ほどで10秒かかるが、**チャットは止めない。**
    作れたことも先生には伝えない（裏で勝手にできていればよい）。

    夜のバッチ（runner の DAILY_JOBS の mypage）も同じ処理を回すので、
    ここが失敗しても翌朝には作られる。
    """
    # TODO: ensure_by_user_id は core 側に移す。
    # router がスクリプトを import しているのは向きとして不自然
    from v2_app.scripts.notion_page_create import ensure_by_user_id

    try:
        url = await ensure_by_user_id(user["notion_page_id"])
    except Exception:
        log.exception("マイページの作成に失敗 telegram_id=%s", telegram_id)
        session.release_lock("mypage", telegram_id)
        return
    finally:
        pass

    if not url:
        session.release_lock("mypage", telegram_id)
        return

    # Redisのキャッシュにも入れる。これが無いと after_save が
    # マイページを見つけられない。
    # ⚠️ 裏で走っている間に先生が別の操作をしてキャッシュが
    # 書き換わっている可能性があるので、取り直してから足す
    current = session.get_user(telegram_id) or user
    current["mypage"] = url
    session.set_user(telegram_id, current)
    log.info("マイページを作った telegram_id=%s", telegram_id)


def _ensure_mypage(inc: Incoming, user: Dict[str, Any]) -> None:
    """マイページが無ければ裏で作り始める。**待たない。**

    同期関数にしてあるのは「await しない」ことを呼び出し側に
    はっきりさせるため。

    ⚠️ Redisの鍵で二重起動を防ぐ。onboard（学校を選んだ直後）と
    show（モード選択を出す時）の両方から呼ばれるので、鍵が無いと
    **マイページが2つできる**（2026-10-13に実機で発生）。
    作成に10秒かかる間はキャッシュの mypage が空なので、
    「空かどうか」だけでは防げない。
    """
    if user.get("mypage"):
        return

    # 5分で切れる。作成中に落ちても次の /new で再試行できる
    if not session.acquire_lock("mypage", inc.telegram_id, ttl=300):
        log.info("マイページの作成が既に走っている telegram_id=%s", inc.telegram_id)
        return

    task = asyncio.create_task(_build_mypage(inc.telegram_id, dict(user)))
    _background.add(task)
    # 終わったら参照を外す。失敗はタスクの中でログに出している
    task.add_done_callback(_background.discard)


async def onboard(inc: Incoming, user: Dict[str, Any]) -> None:
    """所属が決まっていない先生に学校を選ばせる。

    名前は Telegram の first_name / last_name から取れているので聞かない。
    変えたい先生は Settings から直せる。
    """
    if inc.is_callback and inc.text.startswith("school:"):
        log.info("[5] onboard: 学校が選ばれた")
        school_id = inc.text[len("school:"):]
        updated = await user_repo.set_school(inc.telegram_id, school_id)
        if inc.message_id:
            await telegram.edit_message_text(
                inc.chat_id, inc.message_id, updated.get("school_name") or ""
            )
        await telegram.send_message(inc.chat_id, t("school_saved"))
        _ensure_mypage(inc, updated)
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
