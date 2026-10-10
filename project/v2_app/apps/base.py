from __future__ import annotations

import logging
import os
import tempfile
from datetime import date
from typing import Any, Dict, List, Optional, Callable

import httpx

from v2_app.core import (
    ask,
    extract,
    flow,
    media,
    notion_writer,
    session,
    slack,
    stt,
    summarize,
    telegram,
)
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

SAVE = "save"
MORE = "more"

TEXTS: Dict[str, Dict[str, str]] = {
    "saved": {"en": "Saved. Thank you.", "km": "បានរក្សាទុក។ អរគុណ។"},
    "save_failed": {"en": "Could not save. Please try again.", "km": "មិនអាចរក្សាទុកបានទេ។ សូមព្យាយាមម្តងទៀត។"},
    "in_progress": {"en": "Still saving. Please wait.", "km": "កំពុងរក្សាទុក។ សូមរង់ចាំ។"},
    "keep_going": {"en": "Please tell me more.", "km": "សូមប្រាប់ខ្ញុំបន្ថែម។"},
    "no_session": {"en": "Please choose what to record with /start", "km": "សូមជ្រើសរើសអ្វីដែលត្រូវកត់ត្រាដោយប្រើ /start"},
    "btn_save": {"en": "Save", "km": "រក្សាទុក"},
    "btn_more": {"en": "Add more", "km": "បន្ថែមទៀត"},
    "media_failed": {"en": "Could not read that file.", "km": "មិនអាចអានឯកសារនោះបានទេ។"},
    "confirm_head": {"en": "Is this correct?", "km": "តើនេះត្រឹមត្រូវទេ?"},
}


def t(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en}\n{km}" if km else en


def _btn(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en} / {km}" if km else en


def _filled(route: str, telegram_id: int) -> Dict[str, Any]:
    return (session.get_session(route, telegram_id) or {}).get("filled", {})


def _fill_if_present(
    route: str, telegram_id: int, fields: List[flow.Field], values: Dict[str, Any]
) -> None:
    """schema にある key だけ入れる。持っていないモードでは何もしない。"""
    keys = {f["key"] for f in fields}
    session.update_filled(
        route, telegram_id, {k: v for k, v in values.items() if k in keys and v}
    )


def _media_key(fields: List[flow.Field], kind: str) -> Optional[str]:
    """写真を Image、音声を Audio に振り分けるための項目を探す。

    schema.py が source="media" の項目に media_kind を書いておく。
    """
    for f in fields:
        if f.get("source") == "media" and f.get("media_kind") == kind:
            return f["key"]
    return None


async def _store_media(inc: Incoming, fields: List[flow.Field], route: str) -> str:
    """メディアをR2に上げる。音声なら文字起こしして本文を返す。

    返すのは「本文として扱うテキスト」。音声なら文字起こし、
    それ以外は caption（無ければ空）。
    """
    url = await telegram.get_file_url(inc.file_id)

    key = _media_key(fields, inc.kind)
    if key:
        try:
            public_url = await media.upload_from_url(
                url,
                app=route,
                telegram_id=inc.telegram_id,
                kind=inc.kind,
                content_type=inc.mime_type,
            )
            # 同じ項目に複数送れるよう、リストに足す
            current = _filled(route, inc.telegram_id).get(key) or []
            if not isinstance(current, list):
                current = [current]
            session.update_filled(
                route, inc.telegram_id, {key: current + [public_url]}
            )
        except Exception:
            log.exception("R2へのアップロードに失敗 route=%s", route)

    if inc.kind != "voice":
        return inc.text

    # V1の core/audio がファイルパスを受ける作りなので、一度落とす
    path = ""
    try:
        suffix = media._ext("", inc.mime_type) or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            path = tmp.name
            async with httpx.AsyncClient(timeout=180) as client:
                res = await client.get(url)
                res.raise_for_status()
                tmp.write(res.content)

        km, en = await stt.transcribe(path)
    except Exception:
        log.exception("文字起こしに失敗 route=%s", route)
        km, en = "", ""
    finally:
        if path and os.path.exists(path):
            os.unlink(path)

    if not (km or en):
        await telegram.send_message(inc.chat_id, t("media_failed"))
        return ""

    _fill_if_present(
        route, inc.telegram_id, fields, {"stt_km": km, "translated_en": en}
    )
    return stt.main_text(km, en)


async def handle(
    inc: Incoming,
    user: Dict[str, Any],
    *,
    route: str,
    fields: List[flow.Field],
    db_id: str,
    post_to_slack: bool = False,
    before_save: Optional[Callable] = None,
) -> None:
    """3モードが共有する会話ループ。

    各モードの handler.py は route / fields / db_id を埋めて
    これを呼ぶだけにする。
    """
    if session.get_session(route, inc.telegram_id) is None:
        await telegram.send_message(inc.chat_id, t("no_session"))
        session.clear_route(inc.telegram_id)
        return

    # --- ボタン ---
    if inc.is_callback:
        if inc.text == SAVE:
            await _save(inc, user, route=route, fields=fields, db_id=db_id,
                        post_to_slack=post_to_slack)
        elif inc.text == MORE:
            await telegram.send_message(inc.chat_id, t("keep_going"))
        return

    # --- メディア / テキスト ---
    text = inc.text
    if inc.has_media:
        await telegram.send_chat_action(inc.chat_id)
        text = await _store_media(inc, fields, route)
        if not text and inc.kind == "voice":
            return
    
    if inc.text == SAVE:
        await _save(inc, user, route=route, fields=fields, db_id=db_id, post_to_slack=post_to_slack, before_save=before_save)

    if text:
        session.append_history(route, inc.telegram_id, "user", text)
        await telegram.send_chat_action(inc.chat_id)
        try:
            values = await extract.extract_values(
                fields, session.get_history(route, inc.telegram_id), text
            )
            session.update_filled(route, inc.telegram_id, values)
        except Exception:
            log.exception("抽出に失敗 route=%s", route)

    filled = _filled(route, inc.telegram_id)

    # --- 次の問いかけ ---
    ask_count = (session.get_session(route, inc.telegram_id) or {}).get("ask_count", 0)
    question = await ask.make_question(
        fields, filled, session.get_history(route, inc.telegram_id), ask_count
    )
    if question:
        session.bump_ask_count(route, inc.telegram_id)
        session.append_history(route, inc.telegram_id, "assistant", question)
        await telegram.send_message(inc.chat_id, question)
        return

    # ⚠️ make_question の None は「掘り下げを使い切った」と
    # 「LLMが落ちた」の両方で返る。区別できないので充足を確かめる。
    # 未充足なら schema.py の固定の質問に落とす（proposal §4-6）
    if not flow.is_complete(fields, filled):
        fallback = flow.next_question(fields, filled)
        if fallback:
            session.append_history(route, inc.telegram_id, "assistant", fallback)
            await telegram.send_message(inc.chat_id, fallback)
            return

    await _confirm(inc, route, fields, filled)


async def _confirm(
    inc: Incoming, route: str, fields: List[flow.Field], filled: Dict[str, Any]
) -> None:
    body = flow.render_confirmation(fields, filled)
    rows = [[(_btn("btn_save"), SAVE), (_btn("btn_more"), MORE)]]
    await telegram.send_message(
        inc.chat_id,
        f"{t('confirm_head')}\n\n{body}",
        reply_markup=telegram.inline_keyboard(rows),
    )


async def _save(
    inc: Incoming,
    user: Dict[str, Any],
    *,
    route: str,
    fields: List[flow.Field],
    db_id: str,
    post_to_slack: bool,
    before_save: Optional[Callable] = None,
) -> None:
    """保存する。連打はここで止める。"""
    # ⚠️ Notionに触る前に鍵を取る。clear_session だけでは、
    # ほぼ同時の2タップが両方「セッションあり」を読んでしまう
    if not session.acquire_lock("save", inc.telegram_id):
        await telegram.send_message(inc.chat_id, t("in_progress"))
        return

    try:
        if session.get_session(route, inc.telegram_id) is None:
            return

        # 自動で入る項目
        _fill_if_present(route, inc.telegram_id, fields, {
            "date": date.today().isoformat(),
            "teacher": user.get("notion_page_id"),
            "school": user.get("school_id"),
            "external_id": notion_writer.make_external_id(inc.update_id),
        })

        if before_save:
            try:
                await before_save(inc, user)
            except Exception:
                log.exception("before saveに失敗, route=%s", route)

        # AIが埋める項目
        await telegram.send_chat_action(inc.chat_id)
        filled = _filled(route, inc.telegram_id)
        try:
            title = await summarize.make_summary(fields, filled)
            keywords = await summarize.make_keywords(
                flow.render_confirmation(fields, filled)
            )
            _fill_if_present(route, inc.telegram_id, fields, {
                "summary": title, "title": title, "keywords": keywords,
            })
        except Exception:
            log.exception("要約に失敗 route=%s", route)

        filled = _filled(route, inc.telegram_id)
        page_id = await notion_writer.save(db_id, fields, filled)
        log.info("保存した route=%s page=%s", route, page_id)

        # 押したボタンを消す
        done = f"{t('saved')}\n\n{flow.render_confirmation(fields, filled)}"
        if inc.message_id:
            await telegram.edit_message_text(inc.chat_id, inc.message_id, done)
        else:
            await telegram.send_message(inc.chat_id, done)

        if post_to_slack:
            try:
                text = await summarize.make_slack_text(user.get("name", ""), filled)
                if text:
                    await slack.post(text, school_name=user.get("school_name", ""))
            except Exception:
                log.exception("Slack投稿に失敗")

        session.clear_session(route, inc.telegram_id)

    except Exception:
        log.exception("保存に失敗 route=%s", route)
        await telegram.send_message(inc.chat_id, t("save_failed"))
    finally:
        session.release_lock("save", inc.telegram_id)
