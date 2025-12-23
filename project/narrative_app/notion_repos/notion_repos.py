from typing import Optional, Dict, Any, List
import logging
from core.notion_client import get_notion_client
from core.config import (
    NOTION_SCHOOLS_DB_ID,
    NOTION_TEACHERS_DB_ID,
    NOTION_NARRATIVES_DB_ID,
)
from narrative_app.summarization import generate_detailed_content, generate_summary
from urllib.parse import urlparse

from core.telegram_helper import tg_get_file_url
from core.config import NARRATIVE_TELEGRAM_BOT_TOKEN
logger = logging.getLogger(__name__)
narrative_bot_token = NARRATIVE_TELEGRAM_BOT_TOKEN

# School Related
def get_or_create_school_by_chat(chat_id: int, chat_title:str) -> str:
    # Get School DB's ID from Telegram's chat_id/chat_title
    # if no exist, create new page(school) and return the ID
    notion = get_notion_client()
    
    # 1: Search existing Schools
    resp = notion.databases.query(
        **{
            "database_id" : NOTION_SCHOOLS_DB_ID,
            "filter": {
                "property": "Telegram Chat ID",
                "number": {"equals": chat_id},
            },
            "page_size": 1,
        }
    )

    results = resp.get("results", [])
    if results:
        return results[0]["id"]
    
    # if no exist, create new school and return the ID
    create_resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_SCHOOLS_DB_ID},
            "properties": {
                "Name": {"title": [{"text": {"content": chat_title}}]},
                "Telegram Chat ID": {"number": chat_id},
            },
        }
    )
    return create_resp["id"]

# Teacher related
def get_or_create_teacher_by_telegram(
        telegram_user_id: int,
        name: str,
        username:Optional[str],
        school_page_id: str,
) -> str:
    # Get Telegram DB page id from telegram user info
    # if no exist, create new teacher and return the id
    notion = get_notion_client()

    # 1 search existing teacher
    resp = notion.databases.query(
        **{
            "database_id": NOTION_TEACHERS_DB_ID,
            "filter":{
                    "property": "Telegram User ID",
            "number": {"equals": telegram_user_id},
            },
            "page_size": 1,
        },
    )
    results = resp.get("results", [])
    if results:
        return results[0]["id"]
    
    # 2 create new teacher

    props: Dict[str, Any] = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Telegram User ID": {"number": telegram_user_id},
        # Schoolはrelation型を想定
        "School": {
            "relation": [{"id": school_page_id}],
        },
    }

    # if username exists, add 
    if username:
        props["Telegram Username"] = {"rich_text": [{"text": {"content":username}}]}
    
    create_resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_TEACHERS_DB_ID},
            "properties": props,
        }
    )
    return create_resp["id"]

def is_http_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http","https") and bool(u.netloc)
    except Exception:
        return False

# Add summary/detailed/media in "New Practice" of Narrative DB
def append_summary_detail_media_to_narrative_children(
        narrative_page_id : str,
        summary_text: str,
        detailed_text: str,
        media_items: Optional[List[tuple[str,str]]] = None,
)-> None:
    # make three sections on Staff Narrative Page (Summary/Detailed/Media)
    notion = get_notion_client()
    media_blocks: list[dict] = []

    if media_items:
        for kind, maybe_url_or_file_id in media_items:
            kind_lower = (kind or "").lower()
            s = (maybe_url_or_file_id or "").strip()

            if not is_http_url(s):
                try:
                    s = tg_get_file_url(s, narrative_bot_token)
                except Exception as e:
                    logger.exception("Failed to convert file_id to url. kind=%s value=%s err=%s",
                                     kind, maybe_url_or_file_id, e)
                    media_blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{
                            "type": "text",
                            "text": {"content": f"[media skipped] kind={kind} value={maybe_url_or_file_id}"}
                        }]}
                    })
                    continue
            url = s
            logger.info("media kind=%s url=%s", kind, url)

            if "photo" in kind_lower or "image" in kind_lower:
                block_type, body_key = "image", "image"
            elif "video" in kind_lower:
                block_type, body_key = "video", "video"
            else:
                block_type, body_key = "file", "file"

            media_blocks.append({
                "object": "block",
                "type": block_type,
                body_key: {
                    "type": "external",
                    "external": {"url": url},
                },
            })
    else:
        media_blocks.append({
            # If there is no media
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Media section (no photos/videos)"
                        },
                    }
                ]
            },
        })

    children = [
        # Summary
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Summary"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": 
                   summary_text or ""
                
            },
        },
        # Detailed class content
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Detailed Class Content"}}
                ],
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": 
                    detailed_text or "",
                
            },
        },
        # Media
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type":"text", "text":{"content": "Media"}}
                ]
            },
        },
        *media_blocks
    ]

    notion.blocks.children.append(
        **{
            "block_id": narrative_page_id,
            "children": children,
        }
    )

# Update SUbject tags of Narrative DB
def update_narrative_tags(
        narrative_page_id: str,
        subject_tag: str,
) -> None:
    # Set Subject-Tag to NarrativeDB in Notion
    # Existing tags will be updated via this func
    notion = get_notion_client()

    if subject_tag is None:
        subject_select = None
    else:

    # subject_select = [{"name": tag} for tag in subject_tags]
        subject_select = {"name":subject_tag}

    notion.pages.update(
        **{
            "page_id": narrative_page_id,
            "properties": {
                "Subject Tag": {
                    "select":subject_select,
                }
            }
        }
    )


# Narrative related
def get_open_narrative_for_teacher(teacher_page_id:str) -> Optional[Dict[str, Any]]:
    # Check the time-window, if it no closed, return the Narrative for teacher. If no, None
    notion = get_notion_client()

    # Prop: "Teacher"/"Is_Closed"
    resp = notion.databases.query(
        **{
            "database_id": NOTION_NARRATIVES_DB_ID,
            "filter": {
                "and": [
                    {
                        "property":"Teacher",
                        "relation": {
                            "contains": teacher_page_id,
                        },
                    },
                    {
                        "property": "Is Closed",
                        "checkbox": {"equals": False},
                    },
                ]
            },
            "page_size": 1,
        }
    )
    results = resp.get("results",[])
    return results[0] if results else None

# Retrieve Raw text from the "Raw text" paragraph in the one notion page
def get_raw_text_from_narrative(narrative_page_id: str) -> str:
    notion = get_notion_client()

    # get all the block info under the one notion page
    all_blocks = []
    cursor = None

    while True:
        res = notion.blocks.children.list(
            block_id = narrative_page_id,
            start_cursor = cursor,
        )
        all_blocks.extend(res.get("results", []))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")
        
    raw_text = ""

    # Inside the blocks, find the heading-2 named "Raw Text"
    for idx, block in enumerate(all_blocks):
        if block.get("type") == "heading_2":
            rich = block["heading_2"].get("rich_text",[])
            heading_text = "".join(r.get("plain_text","") for r in rich).strip()
            if heading_text == "Raw Text":
                if idx + 1 < len(all_blocks):
                    next_block = all_blocks[idx + 1]
                    if next_block.get("type") == "paragraph":
                        pr = next_block["paragraph"].get("rich_text", [])
                        raw_text = "".join(r.get("plain_text","") for r in pr)
                break
    return raw_text
    

def create_narrative(
        teacher_page_id: str,
        school_page_id: str,
        title: str,
        start_timestamp_iso: str,
        raw_text: str,
)-> str:
    # create new ewcord of Narrative and return the pageid
    # timestamp is ISO8601 (ex, 2025-11-21T12:34:56z)
    notion = get_notion_client()

    props: Dict[str, Any] = {
        "Title": {"title": [{"text": {"content": title}}]},
        "Teacher": {"relation": [{"id": teacher_page_id}]},
        "School": {"relation":[{"id": school_page_id}]},
        "Date": {"date": {"start": start_timestamp_iso}},
        "Is Closed": {"checkbox": False},
    }
    
    resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_NARRATIVES_DB_ID},
            "properties": props,
        }
    )

    # Title children
    children = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Raw Text"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": raw_text or ""}}
                ]
            },
        }
    ]
    # Add "title" to the raw_text into the block in it
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

def append_and_update_narrative_children(narrative_page_id: str, additional_text:str) -> None:
        notion = get_notion_client()

        # find paragpah block of "Raw Text"
        all_blocks = []
        cursor = None
        while True:
          res = notion.blocks.children.list(
              block_id = narrative_page_id,
              start_cursor = cursor,
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
                heading_text = "".join(r.get("plain_text","") for r in rich).strip()
                if heading_text == "Raw Text" and idx + 1 < len(all_blocks):
                    para = all_blocks[idx +1]
                    if para.get("type") == "paragraph":
                        paragraph_block_id = para["id"]
                        pr = para["paragraph"].get("rich_text", [])
                        current_text = "".join(r.get("plain_text","") for r in pr)
                    break
        
        if paragraph_block_id is None:
            # If there is no, no doing anything
            return
        
        new_text = (current_text + "\n" + (additional_text or "")).strip()

        rich_text = text_to_rich_text_blocks(new_text)

        # Update the paragraph block
        notion.blocks.update(
            block_id = paragraph_block_id,
            paragraph = {
                "rich_text": rich_text,
            },
        )
        
def append_media_to_narrative(
        narrative_page_id: str,
        media_url: str,
        name: Optional[str] = None,
) -> None:
    # put ONE url into the Media property of Narrative DB
    # media_url: Telegram's file url
    # name: the displayed name on Notion
    notion = get_notion_client()
    page = notion.pages.retrieve(narrative_page_id)
    props = page.get("properties", {})
    media_prop = props.get("Media", {})

    existing_files = media_prop.get("files", []) or []

    new_file = {
        "name": name or "media",
        "external": {"url": media_url},
    }
    new_files = existing_files + [new_file]

    notion.pages.update(
        **{
            "page_id": narrative_page_id,
            "properties": {
                "Media": {
                    "files": new_files,
                }
            }
        }
    )

def _extract_media_items_from_narrative(page:Dict) -> List[tuple[str,str]]:
    # get {kind, url} and make List from Media property of the Narrative Db
    props = page.get("properties", {})
    media_prop = props.get("Media",{})
    files = media_prop.get("files", []) or []

    items: List[tuple[str,str]] = []

    for f in files:
        name = (f.get("name") or "").lower()
        external = f.get("external") or f.get("file") or {}
        url = external.get("url")
        if not url:
            continue


        if "photo" in name or "image" in name:
            kind = "photo"
        elif "video" in name:
            kind = "video"
        else:
            kind = "file"
        
        items.append({kind, url})
        
    return items


def close_narrative(
        narrative_page_id: str,
        end_timestamp_iso: str,
        # media_items: Optional[List[tuple[str,str]]] = None,
) -> str:
    # Close the existing narrative. Is Closed = True, update Notion property "Date" to "end"
    notion = get_notion_client()

    # Get the start from the existing, from the first message
    page = notion.pages.retrieve(narrative_page_id)
    props = page.get("properties", {})
    date_prop = props.get("Date", {}).get("date",{}) or {}

    # Get start from the first message
    start_timestamp_iso = date_prop.get("start")

    # If there are datas with no start_time, start_time will be end_time
    if not start_timestamp_iso:
        start_timestamp_iso = end_timestamp_iso
    
    # Get the Rawtext
    raw_text = get_raw_text_from_narrative(narrative_page_id)

    # Create Summary / Detailed via LLM
    summary_text = generate_summary(raw_text)
    detailed_text = generate_detailed_content(raw_text)

    # Makling chunks so that it will not exceed 2000 length limit of the str
    chunked_summary_text = text_to_rich_text_blocks(summary_text)
    chunked_detailed_text = text_to_rich_text_blocks(detailed_text)

    media_items = _extract_media_items_from_narrative(page)
    if not media_items:
        logger.info("No media has been uploaded")
    
    # Update the page Summary / Detailed / Media
    append_summary_detail_media_to_narrative_children(
        narrative_page_id=narrative_page_id,
        summary_text=chunked_summary_text,
        detailed_text=chunked_detailed_text,
        media_items=media_items,
    )
    
    notion.pages.update(
        **{
            "page_id": narrative_page_id,
            "properties": {
                "Is Closed": {"checkbox": True},
                "Date": {
                    "date": {
                        "start": start_timestamp_iso,
                        # setting end_timestamp newly
                        "end": end_timestamp_iso,
                    },
                },
            }
        }
    )