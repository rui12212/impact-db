from v1_portfolio.notion.notion_client import get_notion_client
from v1_portfolio.models import TelegramUserInfo, PortfolioDecisionResult
from core.config import (
    PORTFOLIO_TELEGRAM_BOT_TOKEN,
    PORTFOLIO_WINDOW_MINUTES,
    NOTION_TEACHER_PORTFOLIO_DB,
    NOTION_PORTFOLIO_USER_DB,
)
portfolio_bot_token = PORTFOLIO_TELEGRAM_BOT_TOKEN
portfolio_bot_window_minutes = PORTFOLIO_WINDOW_MINUTES
from datetime import datetime, timedelta, timezone
from core.grouping import is_within_window, parse_iso, to_iso
from typing import Optional, Dict, Any, List
from core.audio.stt_translate import portfolio_translate_note_km_to_en

def build_display_name(user: TelegramUserInfo) -> str:
    parts = []
    # userのFirst／Lastnameがあったら、フルネームを作ってリターン
    if user.first_name:
        parts.append(user.first_name)
    if user.last_name:
        parts.append(user.last_name)
    if parts:
        return "".join(parts)
    # 上記がなかったら、user.nameがあればそれをreturn
    if user.username:
        return f"@{user.username}"
    # 上記す全てなかったらidだけを返す
    return f"User{user.user_id}"


# Userがいるかどうかの確認。いなければ新規作成でそのIDを返す。いればそのIDを返す。
def get_or_create_user(user_info: TelegramUserInfo) -> str:
    notion = get_notion_client()
    telegram_user_id = user_info.user_id
    username = user_info.username

    resp = notion.databases.query(
        **{
            "database_id": NOTION_PORTFOLIO_USER_DB,
            "filter": {
                "property": "telegram_user_id",
                "number": {"equals": telegram_user_id},
            },
            "page_size": 1,
        }
    )
    results = resp.get("results", [])
    if results:
        return results[0]["id"]

    name = build_display_name(user_info)

    props: Dict[str, Any] = {
        "name": {"title": [{"text": {"content": name}}]},
        "telegram_user_id": {"number": telegram_user_id},
    }

    if username:
        props["telegram_user_name"] = {"rich_text": [{"text": {"content": username}}]}

    create_user_resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_PORTFOLIO_USER_DB},
            "properties": props,
        }
    )
    return create_user_resp["id"]

def get_open_portfolio_by_teacher(user_id: str) -> Optional[Dict[str, Any]]:
    notion = get_notion_client()

    resp = notion.databases.query(
        **{
            "database_id":NOTION_TEACHER_PORTFOLIO_DB,
            "filter": {
                "and": [
                    {
                        "property": "user",
                        "relation": {
                            "contains": user_id,
                        },
                    },
                    {
                        "property": "is_closed",
                        "checkbox": {"equals": False},
                    }
                ]
            },
            "page_size": 1,
        }
    )
    results = resp.get("results", [])
    return results[0] if results else None

def create_portfolio(
    user_id: str,
    summary: str,
    start_timestamp_iso: datetime,
    text: Optional[str] = None,
    sound_file: Optional[str] = None,
    media_file: Optional[str] = None,
) -> str:
     notion = get_notion_client()

     props: Dict[str, Any] = {
        "summary": {"title": [{"text": {"content": summary}}]},
        "created_at": {"date": {"start": start_timestamp_iso}},
        "user": {"relation": [{"id": user_id}]},
        "note": {"rich_text": [{"text": {"content": text or ""}}]},
        "sound_file": {"files": [{"name": "sound_file", "external": {"url": sound_file}}] if sound_file else []},
        "is_closed": {"checkbox": False},
     }

     resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_TEACHER_PORTFOLIO_DB},
            "properties": props,
        }
     )

     children = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "New memo"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": text or ""}}
                ]
            },
        }
    ]

     notion.blocks.children.append(
        **{
            "block_id": resp["id"],
            "children": children,
        }
     )
     return resp["id"]


def text_to_rich_text_blocks(text: str, chunk: int=1900) -> list[dict]:
    s = (text or "")
    parts = [s[i:i+chunk] for i in range(0, len(s), chunk)] or [""]
    return [
        {"type": "text", "text":{"content": p}}
        for p in parts
    ]

def append_and_update_portfolio_children(portfolio_page_id: str, additional_text: str, sound_file: Optional[str] = None) -> None:
    notion = get_notion_client()

    # WHEN TEXT ADDED
    all_blocks = []
    cursor = None
    while True:
        res = notion.blocks.children.list(
            block_id=portfolio_page_id,
            start_cursor=cursor,
        )
        all_blocks.extend(res.get("results",[]))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    paragraph_block_id = None
    current_text = ""

    for idx, block in enumerate(all_blocks):
        if block.get("type") == "heading_2":
            rich = block["heading_2"].get("rich_text", [])
            heading_text = "".join(r.get("plain_text", "") for r in rich).strip()
            if heading_text == "New memo" and idx +1 < len(all_blocks):
                para=all_blocks[idx+1]
                if para.get("type") == "paragraph":
                    paragraph_block_id = para["id"]
                    pr = para["paragraph"].get("rich_text", [])
                    current_text="".join(r.get("plain_text", "") for r in pr)
                break
    if paragraph_block_id is None:
        return

    new_text=(current_text + "\n" + (additional_text or "")).strip()

    rich_text = text_to_rich_text_blocks(new_text)

    notion.blocks.update(
        block_id = paragraph_block_id,
        paragraph = {
            "rich_text": rich_text
        }
    )

    # UPDATE note property (always) and sound_file (if present)
    props_to_update: Dict[str, Any] = {
        "note": {"rich_text": text_to_rich_text_blocks(new_text)},
    }

    if sound_file:
        page = notion.pages.retrieve(portfolio_page_id)
        existing = page.get("properties", {}).get("sound_file", {}).get("files", []) or []
        props_to_update["sound_file"] = {
            "files": existing + [{"name": "sound_file", "external": {"url": sound_file}}],
        }

    notion.pages.update(
        **{
            "page_id": portfolio_page_id,
            "properties": props_to_update,
        }
    )



# case1: UserがStartを忘れてアップロードした場合：
# IsOpenがあるかどうかー＞その後1時間以内かどうか、Notion継続でそのままデータのアップロード
def decide_and_get_or_create_portfolio(
    user_id: str,
    message_dt: datetime,
    text: Optional[str] = None,
    sound_file: Optional[str] = None,
) -> PortfolioDecisionResult:
    if message_dt.tzinfo is None:
        message_dt = message_dt.replace(tzinfo=timezone.utc)

    open_portfolio = get_open_portfolio_by_teacher(user_id)

    #  1: No Open portfolio-> create new Portfolio record
    if open_portfolio is None:
        start_iso = to_iso(message_dt)
        summary = "New Record"
        portfolio_page_id = create_portfolio(
            user_id=user_id,
            summary=summary,
            start_timestamp_iso=start_iso,
            text=text,
            sound_file=sound_file,
        )
        return PortfolioDecisionResult(
            portfolio_page_id=portfolio_page_id,
            is_new=True,
            started_at=message_dt,
            needs_confirmation=False,
        )

    # 2: Open Narrative DB -> check the time-window
    # created_at ではなく last_edited_time を使うことで、継続してデータを追加した場合に
    # ウィンドウがリセットされ、毎回確認ダイアログが出るのを防ぐ
    last_edited_str: Optional[str] = open_portfolio.get("last_edited_time")
    if not last_edited_str:
        first_ts = message_dt
    else:
        first_ts = parse_iso(last_edited_str)

    # 2.1 Open Exists but WITHIN 1 hour
    if is_within_window(
        bot_window_minutes=portfolio_bot_window_minutes,
        first_timestamp= first_ts,
        new_timestamp= message_dt,
    ):
        portfolio_page_id = open_portfolio["id"]
        append_and_update_portfolio_children(
            portfolio_page_id=portfolio_page_id,
            additional_text=text,
            sound_file=sound_file,
        )
        return PortfolioDecisionResult(
            portfolio_page_id=portfolio_page_id,
            is_new= False,
            started_at= first_ts,
            needs_confirmation=False,
        )

    # 2.2: Open Exists but OUT OF 1 hour
    else:
        return PortfolioDecisionResult(
            portfolio_page_id= open_portfolio["id"],
            is_new=False,
            started_at=first_ts,
            needs_confirmation=True,
        )



def translate_note_and_update_translated_note(portfolio_page_id:str) -> None:
    notion = get_notion_client()
    page = notion.pages.retrieve(portfolio_page_id)
    note_blocks = page.get("properties", {}).get("note", {}).get("rich_text",[]) or []
    note = "".join(r.get("plain_text","") for r in note_blocks)

    translated_note = portfolio_translate_note_km_to_en(note, "gpt-4.1-mini")

    notion.pages.update(
        **{
            "page_id": portfolio_page_id,
            "properties": {
                "translated_note": {
                    "rich_text": text_to_rich_text_blocks(translated_note or ""),
                }
            }
        }
     )



# UserIDを元に、Openなレコードを最大 limit 件まで取得して全てCloseにする。
# 通常はOpenレコードは1件のみのはずだが、万が一複数存在した場合も limit 件まで安全に閉じる。
def check_and_close_portfolio(user_id: str, limit: int = 5) -> List[str]:
    notion = get_notion_client()

    resp = notion.databases.query(
        **{
            "database_id": NOTION_TEACHER_PORTFOLIO_DB,
            "filter": {
                "and": [
                    {"property": "user", "relation": {"contains": user_id}},
                    {"property": "is_closed", "checkbox": {"equals": False}},
                ]
            },
            "page_size": limit,
        }
    )

    closed_page_list: List[str] = []
    for page in resp.get("results", []):
        closed_page_list.append(page["id"])
        notion.pages.update(
            **{
                "page_id": page["id"],
                "properties": {"is_closed": {"checkbox": True}},
            }
        )
    return closed_page_list

# UserIDをもとに、新規のPortfolioを作成
# →Text \Video \Photo／Soundfileの処理がはいる

def append_media_blocks_to_children(
    portfolio_page_id: str,
    media_items: list[tuple[str, str]],  # (kind, url)
) -> None:
    """Add a 'Media' heading_3 + image/video blocks to page children."""
    notion = get_notion_client()
    blocks: list[Dict[str, Any]] = [
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "Media"}}]
            },
        }
    ]
    for kind, url in media_items:
        block_type = "image" if kind == "photo" else "video"
        blocks.append({
            "object": "block",
            "type": block_type,
            block_type: {
                "type": "external",
                "external": {"url": url},
            },
        })
    notion.blocks.children.append(
        **{
            "block_id": portfolio_page_id,
            "children": blocks,
        }
    )


def append_media_to_portfolio(
    portfolio_page_id: str,
    media_url: str,
    name: Optional[str] = None,
) -> None:
     notion = get_notion_client()
     page = notion.pages.retrieve(portfolio_page_id)
     props = page.get("properties", {})
     media_prop = props.get("media")

     existing_files = media_prop.get("files", []) or []

     new_file = {
        "name": name or "media",
        "external": {"url": media_url},
     }
     new_files = existing_files + [new_file]

     notion.pages.update(
        **{
            "page_id": portfolio_page_id,
            "properties": {
                "media": {
                    "files": new_files,
                }
            }
        }
     )
