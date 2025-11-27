from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone
import logging

from narrative_app.notion_repos import (
    get_or_create_school_by_chat,
    get_or_create_teacher_by_telegram,
    get_open_narrative_for_teacher,
    create_narrative,
    append_to_narrative,
    close_narrative,
)

from narrative_app.grouping import is_within_window, parse_iso, to_iso

logger = logging.getLogger(__name__)

@dataclass
class TelegramUserInfo:
    # The minimus data set of User from the Telegram
    user_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

@dataclass
class TelegramChatInfo:
    # The info of Telegram group chat
    chat_id: int
    title: str

def build_display_name(user: TelegramUserInfo) -> str:
    # Create display name on Notion
    # 1: Firstname + Last name on the Telegram setting of indivisual
    # 2: If no1, username
    # 3: If no 1 & 2, user_id
    parts = []
    if user.first_name:
        parts.append(user.first_name)
    if user.last_name:
        parts.append(user.last_name)
    
    if parts:
        return "".join(parts)
    
    if user.username:
        return f"@{user.username}"
    
    return f"User {user.user_id}"

def resolve_school(chat: TelegramChatInfo) -> str:
    # Get school name from Telegram chat group and return the Notion Schools DB page's ID
    # if no, create new school page
    school_page_id = get_or_create_school_by_chat(
        chat_id = chat.chat_id,
        chat_title = chat.title
    )
    return school_page_id

def resolve_teacher(user: TelegramUserInfo, school_page_id:str) -> str:
    # Return the Teacher DB ID based on the Telegram User Info and connected School Id to it (Telegram User Info)
    display_name = build_display_name(user)
    teacher_page_id = get_or_create_teacher_by_telegram(
        telegram_user_id = user.user_id,
        name = display_name,
        username = user.first_name,
        school_page_id = school_page_id,
    )
    return teacher_page_id


@dataclass
class NarrativeDecisionResult:
    # the class for hold the result how the transaction of data goes
    narrative_page_id: str
    is_new: bool
    started_at: datetime


def decide_and_get_narrative(
        teacher_page_id: str,
        school_page_id: str,
        message_dt: datetime,
        text: str,        
) -> NarrativeDecisionResult:
    # About the specific teacher,
    # if it is within the time-window, add data to the existing&open Narraive DB
    # if not, close the existing Narrative DB and create new record tot the page, and return Narrative ID
    
    # message_dt is timezone-aware(UTC)
    if message_dt.tzinfo is None:
        message_dt = message_dt.replace(tzinfo=timezone.utc)
    
    open_narrative = get_open_narrative_for_teacher(teacher_page_id)

    # 1: No Open Narrative -> Create New one
    if open_narrative is None:
        start_iso = to_iso(message_dt)
        title = "New Practice"
        narrative_page_id = create_narrative(
            title = title,
            teacher_page_id=teacher_page_id,
            school_page_id=school_page_id,
            start_timestamp_iso = start_iso,
            raw_text=text,
        )
        return NarrativeDecisionResult(
            narrative_page_id=narrative_page_id,
            is_new=True,
            started_at=message_dt,
        )
    
    # 2: Open Narrative DB -> check the time-window
    props = open_narrative.get("properties",{})
    date_prop = props.get("Date",{}).get("date",{})

    start_str: Optional[str] = date_prop.get("start")
    if not start_str:
        # if there is no start added accidentaly, newest messsage's start will be added
        first_ts = message_dt
    else:
        first_ts = parse_iso(start_str)
    
    # check the time-window is within or not
    if is_within_window(first_ts, message_dt):
        # if it is within time-window, update and add raw text
        narrative_page_id = open_narrative["id"]
        append_to_narrative(
            narrative_page_id = narrative_page_id,
            additional_text=text,
        )
        return NarrativeDecisionResult(
            narrative_page_id=narrative_page_id,
            is_new=False,
            started_at = first_ts,
        )
    
    # 3: when the time-window is out-> close the Old Narrative and create new record
    narrative_page_id_old = open_narrative["id"]
    end_iso = to_iso(message_dt)
    close_narrative(
        narrative_page_id=narrative_page_id_old,
        end_timestamp_iso=end_iso,
    )

    # create New narrative
    start_iso_new=to_iso(message_dt)
    title- "New Practice"
    narrative_page_id_new = create_narrative(
        teacher_page_id=teacher_page_id,
        school_page_id=school_page_id,
        title=title,
        start_timestamp_iso=start_iso_new,
        raw_text=text,
    )

    return NarrativeDecisionResult(
        narrative_page_id=narrative_page_id_new,
        is_new=True,
        started_at=message_dt,
    )

def handle_telegram_update(update:dict) -> None:
    # Receive the Update(JSON) and,
    # school/teacher will be recorded automatically
    # target specific Narrative, and save the text

    # 25th Nov 2025: Support Only text
    # Music/Video/Voice will be coded later
    try:
        message=update.get("message") or update.get("edited_massage")
        if not message:
             logger.info("No message in update, skipping. update_keys=%s", list(update.keys()))
             return
        
        from_user = message["from"]
        chat = message["chat"]

        # Date info from Telegram is UTC(Unix minutes)
        date_ts = message.get("date")
        if date_ts is None:
            # just in case, fallback with current time
            message_dt = datetime.now(timezone.utc)
        else:
            message_dt = datetime.fromtimestamp(date_ts, tz=timezone.utc)
        
        # Set text from the telegram to the narrative DB
        text = message.get("text") or ""
        if not text:
            # Music/Pics/Videos will be added later
            logger.info("No text in message. Skipping for now")
            return 
        
        user_info = TelegramUserInfo(
            user_id= from_user["id"],
            first_name=from_user.get("first_name", ""),
            last_name=from_user.get("last_name"),
            username=from_user.get("username"),
        )

        chat_info = TelegramChatInfo(
            chat_id=chat["id"],
            title=chat.get("title") or chat.get("username") or "Unknown school name"
        )

        # Schoool/Teacher update or create new
        school_id = resolve_school(chat_info)
        teacher_id = resolve_teacher(user_info, school_id)

        result = decide_and_get_narrative(
            teacher_page_id=teacher_id,
            school_page_id=school_id,
            message_dt=message_dt,
            text=text,
        )

        logger.info(
            "Saved narrative: page_id=%s is_new=%s, started_at=%s",
            result.narrative_page_id,
            result.is_new,
            result.started_at.isoformat(),
        )
    except Exception as e:
        logger.exception("Exception while handling Telegram update: %s", e)
        # exception will be handled by putting log in the logger
        # return 200 to telegram anyway