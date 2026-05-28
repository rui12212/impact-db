import json
import logging
import os
import tempfile
import threading
import requests
from datetime import datetime, timezone
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from core.audio.helpers_audio import pick_audio_from_message
from core.audio.stt_translate import oai_transcribe, oai_translate_km_to_en, decide_transcribe_model
from zoneinfo import ZoneInfo
from core.config import (PORTFOLIO_TELEGRAM_BOT_TOKEN, PORTFOLIO_TIMEZONE)
from core.locks import get_teacher_lock
from core.telegram_helper import tg_get_file_url, tg_send_message
from v1_portfolio.models import TelegramUserInfo, PortfolioDecisionResult
from v1_portfolio.notion.notion_repos import (
    append_and_update_portfolio_children,
    append_media_blocks_to_children,
    check_and_close_portfolio,
    create_portfolio,
    decide_and_get_or_create_portfolio,
    get_or_create_user,
    to_iso,
    append_media_to_portfolio,
    translate_note_and_update_translated_note,
)
from core.r2_client import upload_from_url, upload_from_path
import asyncio
from collections import OrderedDict

_processed_msgs: OrderedDict[int, float] = OrderedDict()
_MSG_TTL=300
_MSG_MAX =1000

logger = logging.getLogger(__name__)
portfolio_bot_token = PORTFOLIO_TELEGRAM_BOT_TOKEN
# ０：new/help以外のコマンドラインは常にhelpが発生するようにする

# -----Command Line-----
HELP_TEXT = """\
/help - Show this command line
/new  - Finish past recording and start a new one\
"""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("New recording started!✏️ \n You can post Text/Voice/Video/Photos🎙️")
    # TelegramユーザーIDからNotion user_idを取得し、Openなレコードを全てClose
    from_user = update.message.from_user
    user_info = TelegramUserInfo(
        user_id=from_user.id,
        first_name=from_user.first_name or "",
        last_name=from_user.last_name or "no lastname set",
        username=from_user.username or "no user name set",
    )
    notion_user_id = get_or_create_user(user_info)
    
    closed_page_list = check_and_close_portfolio(notion_user_id)
    for page in closed_page_list:
        translate_note_and_update_translated_note(page)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def handle_command(update_data: dict) -> None:
    app = ApplicationBuilder().token(portfolio_bot_token).build()

    app.add_handler(CommandHandler("help", help_command))
    # Telegramはコマンドを小文字に正規化するため /New /NEW なども /new として受け付けられる
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    async with app:
        update = Update.de_json(update_data, app.bot)
        await app.process_update(update)



# -----When the the callback_query were sent by user through InlineButton-----
pending_store: dict[int, dict] = {}

# making time buffer depends on each media_group_id
# this is to add captions at the bottomn of the each Photos/Videos files on children, when user send several photos and videos at the same time
media_group_buffer: dict[str, dict] = {}
media_group_lock =asyncio.Lock()
MEDIA_GROUP_DEBOUCE_SEC = 3.0


async def _buffer_media_group(message:dict) -> None:
    # """media_group_id 付き update を一時バッファに溜め、debounce後に一括処理する"""
    media_group_id = message["media_group_id"]
    # extract media files from update
    media_files: list[tuple[str, str]] = []

    photos = message.get("photo") or []
    if photos and "file_id" in photos[-1]:
        media_files.append(("photo", photos[-1]["file_id"]))

    video = message.get("video")
    if video and "file_id" in video:
        media_files.append(("video", video["file_id"]))
    doc = message.get("document")
    if doc and "file_id" in doc:
        mime = (doc.get("mime_type") or "").lower()
        if mime.startswith("image/"):
            media_files.append(("photo", doc["file_id"]))
        elif mime.startswith("video/"):
            media_files.append(("video", doc["file_id"]))
    
    caption = message.get("caption")

    async with media_group_lock:
        buf = media_group_buffer.get(media_group_id)
        if buf is None:
            buf = {
                "first_message": message,
                "media_files": [],
                "caption": None,
                "task": None,
            }
            media_group_buffer[media_group_id] = buf
        
        buf["media_files"].extend(media_files)
        if caption and not buf["caption"]:
            buf["caption"] = caption
        
        # cancel the existing task and make new task
        if buf["task"] and not buf["task"].done():
            buf["task"].cancel()

        buf["task"] = asyncio.create_task(_flush_media_group(media_group_id))

async def _flush_media_group(media_group_id: str) -> None:
    try:
        await asyncio.sleep(MEDIA_GROUP_DEBOUCE_SEC)
    except asyncio.CancelledError:
        return
    
    async with media_group_lock:
        buf = media_group_buffer.pop(media_group_id, None)
    
    if not buf or not buf["media_files"]:
        return
    
    try:
        await _process_album(
            first_message=buf["first_message"],
            media_files=buf["media_files"],
            caption=buf["caption"],
        )
    except Exception:
        logger.exception("Failed to flush media group %s", media_group_id)

async def _process_album(
    first_message: dict,
    media_files: list[tuple[str, str]],
    caption: Optional[str],
) -> None:
    # apply the data handling of handle_telegram_update to the album(dealing with bulk of media/caption)
    from_user = first_message["from"]
    chat = first_message["chat"]
    date_ts = first_message.get("date")
    message_dt = (
        datetime.fromtimestamp(date_ts, tz=timezone.utc)
        if date_ts is not None
        else datetime.now(timezone.utc)
    )

    user_info = TelegramUserInfo(
        user_id=from_user["id"],
        first_name=from_user.get("first_name",""),
        last_name=from_user.get("last_name", "no lastname set"),
        username=from_user.get("username", "no username set"),
    )

    user_id = get_or_create_user(user_info)
    user_lock = get_teacher_lock(user_id)

    with user_lock:
        result = decide_and_get_or_create_portfolio(
            user_id=user_id,
            message_dt=message_dt,
            text="",
            sound_file=""
        )
    
    portfolio_page_id = result.portfolio_page_id

    if result.needs_confirmation:
        existing = pending_store.get(from_user["id"])
        if existing:
            existing["media_files"].extend(media_files)
            if caption and not existing.get("caption"):
                existing["caption"] = caption
            return
        
        pending_store[from_user["id"]] = {
            "portfolio_page_id": portfolio_page_id,
            "text": "",
            "media_files": media_files,
            "caption": caption,
            "sound_file": "",
            "started_at": result.started_at,
            "notion_user_id": user_id,
            "date": "Note-" + message_dt.astimezone(ZoneInfo(PORTFOLIO_TIMEZONE)).strftime("%d/%m/%Y,%H:%M"),
        }
        bot = Bot(token=portfolio_bot_token)
        keyboard = [[
            InlineKeyboardButton("CONTINUE🏃‍♀️‍➡️", callback_data="continue"),
            InlineKeyboardButton("START NEW✏️", callback_data="finish"),
        ]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await bot.send_message(
            chat_id=chat["id"],
            text="You left recording for long time...!\nDo you want to CONTINUE previous session?\nor START NEW records?",
            reply_markup=reply_markup,
        )
        return
    
    _append_media_files(portfolio_page_id, media_files, caption=caption)

    tg_send_message(
        chat_id=chat["id"],
        token=portfolio_bot_token,
        text="Data recorded ✏️",
    )



def _append_media_files(portfolio_page_id: str, media_files: list[tuple[str, str]], caption: Optional[str] = None,) -> None:
    resolved: list[tuple[str, str]] = []
    for kind, file_id in media_files:
        try:
            tg_url = tg_get_file_url(file_id,portfolio_bot_token)
            if kind == "photo":
                r2_url = upload_from_url(tg_url, f"photo_{file_id}.jpg", "image/jpeg")
            else:
                r2_url = upload_from_url(tg_url, f"video_{file_id}.mp4", "video/mp4")
            name = "Photo" if kind == "photo" else "Video"
            append_media_to_portfolio(
                portfolio_page_id=portfolio_page_id,
                media_url=r2_url,
                name=name,
            )
            resolved.append((kind, r2_url))
            logger.info("Append media to portfolio=%s kind=%s", portfolio_page_id, kind)
        except Exception:
            logger.exception("Failed to append media kind=%s file_id=%s to portfolio %s", kind, file_id, portfolio_page_id)
    if resolved:
        try:
            append_media_blocks_to_children(
                portfolio_page_id=portfolio_page_id,
                media_items=resolved,
                caption=caption,
            )
        except Exception:
            logger.exception("Failed to append media blocks to children for portfolio %s", portfolio_page_id)


async def handle_callback_query(update: dict) -> None:
    callback = update.get("callback_query", {})
    callback_id = callback.get("id")
    callback_data = callback.get("data")
    from_user = callback.get("from", {})
    telegram_user_id = from_user["id"]
    message = callback.get("message", {}) or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    bot = Bot(token=portfolio_bot_token)

    # 1) ボタンのスピナーを即時解除（再タップ抑止のため最優先）
    if callback_id:
        try:
            await bot.answer_callback_query(
                callback_query_id=callback_id,
                text="Recording Data Now...",
                show_alert=True,
            )
        except Exception:
            logger.exception("Failed to answer callback query id=%s", callback_id)

    # 2) インラインキーボードを除去して以後のタップを防ぐ
    if chat_id and message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )
        except Exception:
            # 二重実行で既に消えているケースなどは無視
            logger.exception("Failed to remove inline keyboard chat=%s message=%s", chat_id, message_id)

    pending = pending_store.pop(telegram_user_id, None)
    if pending is None:
        # expired or unexpected callback
        tg_send_message(
            chat_id=chat_id,
            token=portfolio_bot_token,
            text="Recording failed. Please send message/voice/media files again."
        )
        return
    
    if callback_data == "continue":
        # add to existing record
        append_and_update_portfolio_children(
            portfolio_page_id=pending["portfolio_page_id"],
            additional_text=pending["text"],
            sound_file=pending["sound_file"],
        )
        _append_media_files(pending["portfolio_page_id"], pending["media_files"],caption=pending.get("caption"))
        tg_send_message(
            chat_id=chat_id,
            token=portfolio_bot_token,
            text="Data added to the PAST recording🏃‍♀️‍➡️",
        )
    
    elif callback_data == "finish":
        # 新規レコード作成前に既存のOpenレコードを全てClose
        closed_page_list = check_and_close_portfolio(pending["notion_user_id"])
        for page in closed_page_list:
            translate_note_and_update_translated_note(page)
        
        portfolio_page_id = create_portfolio(
            user_id=pending["notion_user_id"],
            summary=pending["date"],
            start_timestamp_iso=to_iso(datetime.now(timezone.utc)),
            text=pending["text"],
            sound_file=pending["sound_file"],
        )
        _append_media_files(portfolio_page_id, pending["media_files"], caption=pending.get("caption"))

        tg_send_message(
            chat_id=chat_id,
            token=portfolio_bot_token,
            text="Data added to the NEW recording✏️"
        )

def _is_duplicate(message_id:int) -> bool:
    import time
    now = time.time()
    while _processed_msgs:
        _, ts = next(iter(_processed_msgs.items()))
        if now - ts > _MSG_TTL:
            _processed_msgs.popitem(last=False)
        else:
            break
    if message_id in _processed_msgs:
        return True
    
    _processed_msgs[message_id] = now
    if len(_processed_msgs) > _MSG_MAX:
        _processed_msgs.popitem(last=False)
    return False


# -----When Text/Audio/Video/Photo recieved-----
async def handle_telegram_data(update: dict) -> None:
    try:
        message=update.get("message") or update.get("edited_message")
        if not message:
            logger.info("No message in update, skipping. update_keys=%s", list(update.keys()))
            return
        
        msg_id = message.get("message_id")
        if msg_id and _is_duplicate(msg_id):
            logger.info("Duplicate message_id=%s, skipping", msg_id)
            return
        
        # if user send buk photos/videos and caption at the same time, store that to the buffer and debounce. and deal with it at once later
        if message.get("media_group_id"):
            await _buffer_media_group(message)
            return

        from_user= message["from"]
        chat=message["chat"]

        date_ts=message.get("date")
        if date_ts is None:
            # just in case, fallback to the current time
            message_dt=datetime.now(timezone.utc)
        else:
            message_dt=datetime.fromtimestamp(date_ts, tz=timezone.utc)

        # Voice message & Text Message -> SST and Translate
        text = message.get("text")
        caption = message.get("caption")
        file_url = ""
        note_text=""
        translated_note_text = ""


        logger.info("message_keys=%s", list(message.keys()))
        logger.info("has_photo=%s has_video=%s has_document=%s has_new_chat_photo=%s",
        "photo" in message, "video" in message, "document" in message, "new_chat_photo_photo" in message)

        if text:
            note_text = text

        if not text:
            voice = pick_audio_from_message(message)
            description = "Your task is to transcribe the audio data. Please transcribe it according to the following conditions:① For Khmer (language=km), transcribe it as is.② For English (En), transcribe it as is."
            if voice and "file_id" in voice:
                file_id=voice["file_id"]
                logger.info("Received voice message, file_id=%s", file_id)

                tg_url=tg_get_file_url(file_id, portfolio_bot_token)
                with tempfile.TemporaryDirectory() as td:
                    original_name=voice.get("file_name") or "in.bin"
                    src=os.path.join(td, original_name)
                    with requests.get(tg_url, stream=True, timeout=180) as r:
                        r.raise_for_status()
                        with open(src,'wb') as f:
                            for chunk in r.iter_content(8192):
                                f.write(chunk)
                    # note_text = oai_transcribe(src, description)
                    stt_km, translated_en = decide_transcribe_model(src) 
                    note_text = stt_km
                    translated_note_text = translated_en
                    ext = os.path.splitext(original_name)[1] or ".ogg"
                    file_url = await asyncio.to_thread(upload_from_path, src, f"audio_f{file_id}{ext}", "audio/ogg")

        
        # photo/video
        media_files: list[tuple[str,str]] = []

        photos = message.get("photo") or []
        if photos:
            largest_photo = photos[-1]
            if "file_id" in largest_photo:
                media_files.append(("photo", largest_photo["file_id"]))

        video = message.get("video")
        if video and "file_id" in video:
            media_files.append(("video", video["file_id"]))

        # document(such as audio files)
        doc = message.get("document")
        if doc and "file_id" in doc:
            mime= (doc.get("mime_type") or "").lower()
            file_name=(doc.get("file_name") or "").lower()

            if mime.startswith("image/"):
                media_files.append(("photo", doc["file_id"]))
            elif mime.startswith("video/"):
                media_files.append(("video", doc["file_id"]))
            elif mime.startswith("audio/") or file_name.endswith((".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".opus")):
                tg_url= tg_get_file_url(doc["file_id"], portfolio_bot_token)
                doc_file_name = doc.get("file_name") or "document.bin"
                with tempfile.TemporaryDirectory() as td:
                    src = os.path.join(td, doc_file_name)
                    with requests.get(tg_url, stream=True, timeout=180) as r:
                        r.raise_for_status()
                        with open(src, "wb") as f:
                            for chunk in r.iter_content(8192):
                                f.write(chunk)
                        # note_text = oai_transcribe(src)
                        stt_km, translated_en = decide_transcribe_model(src)
                        note_text = stt_km
                        translated_note_text = translated_en
                        file_url = upload_from_path(src, f"audio_{doc[file_id]}_{doc_file_name}", mime or "audio/mpeg")

            else:
                # if mime_type is empty or unclear, making sure with the extension
                if file_name.endswith((".jpg", ".jpeg", ".png", ".JPEG", ".JPG", ".PNG", ".webp", ".heic", ".HEIC")):
                    media_files.append(("photo", doc["file_id"]))
                elif file_name.endswith((".mp4", ".mov", ".MP4", ".MOV", ".m4v", ".M4V", "webm", "WEBM")):
                    media_files.append(("video", doc["file_id"]))
                else:
                    media_files.append(("document", doc["file_id"]))

        if not note_text and not media_files and not file_url:
            logger.info("No usable text or media in message. Skipping")
            return

        user_info=TelegramUserInfo(
            user_id=from_user["id"],
            first_name=from_user.get("first_name", ""),
            last_name=from_user.get("last_name", "no lastname set"),
            username=from_user.get("username", "no user name set")
        )

        # user update or create new
        user_id=get_or_create_user(user_info)

        user_lock=get_teacher_lock(user_id)

        with user_lock:
            result = decide_and_get_or_create_portfolio(
                user_id=user_id,
                message_dt=message_dt,
                text=note_text,
                sound_file=file_url,
                translated_note=translated_note_text 
                
            )

        # tg_send_message(
        #     chat_id=chat["id"],
        #     token=portfolio_bot_token,
        #     text="Recodding Suucess✏️"
        # )
        
        logger.info(
            "Saved narrative: page_id=%s is_new=%s, started_at=%s, needs_confirmation=%s",
            result.portfolio_page_id,
            result.is_new,
            result.started_at.isoformat(),
            result.needs_confirmation,
            )
        
        portfolio_page_id = result.portfolio_page_id

        # InlineKeyboardでのYES＿NOの確認が必要な場合＝OPENで1時間以上経っている時
        # メディアはユーザーの選択後に追加するため、ここでは追加しない
        if result.needs_confirmation:
            existing = pending_store.get(from_user["id"])

            if existing:
                existing["media_files"].extend(media_files)
                if caption and not existing.get("caption"):
                    existing["caption"] = caption
                if note_text:
                    existing["text"] = (existing["text"] + "\n" + note_text).strip()
                if file_url and not existing["sound_file"]:
                    existing["sound_file"] = file_url
                return

            pending_store[from_user["id"]] = {
                "portfolio_page_id": portfolio_page_id,
                "text": note_text,
                "media_files": media_files,
                "caption":caption,
                "sound_file": file_url,
                "started_at": result.started_at,
                "notion_user_id": user_id,
                "date": "Note-" + message_dt.astimezone(ZoneInfo(PORTFOLIO_TIMEZONE)).strftime("%d/%m/%Y,%H:%M"),
            }
            bot = Bot(token=portfolio_bot_token)
            keyboard =[
                [
                    InlineKeyboardButton("CONTINUE🏃‍♀️‍➡️", callback_data="continue"),
                    InlineKeyboardButton("START NEW✏️", callback_data="finish"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await bot.send_message(chat_id=chat["id"], text='You left recording for long time...!\nDo you want to CONTINUE previous session?\nor START NEW records?', reply_markup=reply_markup)

            # tg_send_message(
            #     chat_id=chat["id"],
            #     token=portfolio_bot_token,
            #     text="Do you want to start new recording/ or continue adding data?",
            #     reply_markup=keyboard.to_dict(),
            # )
            return

        # Add Media(photo/video) to Media Property on Narrative DB
        _append_media_files(portfolio_page_id, media_files, caption=caption)

        tg_send_message(
            chat_id=chat["id"],
            token=portfolio_bot_token,
            text="Data recorded ✏️",
        )
    except Exception:
        logger.exception("handle_telegram_data failed")


