from typing import Optional, Dict, Any

from core.notion_client import get_notion_client
from core.config import (
    NOTION_SCHOOLS_DB_ID,
    NOTION_TEACHERS_DB_ID,
    NOTION_NARRATIVES_DB_ID,
)

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
        "Raw Text": {"rich_text": [{"text":{"content": raw_text}}]},
        "Is Closed": {"checkbox": False},
    }

    resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_NARRATIVES_DB_ID},
            "properties": props,
        }
    )
    return resp["id"]

def append_to_narrative(
        narrative_page_id: str,
        additional_text: str,) -> None:
    # Add text to the Rawtext of existing Narraive
    notion = get_notion_client()

    # Get the Rawtext
    page = notion.pages.retrieve(narrative_page_id)
    props = page.get("properties", {})
    rich = props.get("Raw Text",{}).get("rich_text",[])

    current_text = "".join([r.get("plain_text","") for r in rich])
    new_text = (current_text + "\n" + additional_text).strip()

    notion.pages.update(
        **{
            "page_id": narrative_page_id,
            "properties": {
                "Raw Text": {
                    "rich_text": [{"text": {"content": new_text}}],
                }
            }
        }
    )

def close_narrative(
        narrative_page_id: str,
        end_timestamp_iso: str,
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