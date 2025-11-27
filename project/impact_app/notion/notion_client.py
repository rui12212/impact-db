import os, json
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from core.notion_client import get_notion_client
# from notion_client import Client as Notion
from dotenv import load_dotenv
load_dotenv()


REG_PATH = Path(".runtime/chat_registry.json")
REG_PATH.parent.mkdir(parents=True, exist_ok=True)

notion_client = get_notion_client()
NOTION_ROOT_PAGE_ID = os.getenv("NOTION_ROOT_PAGE_ID")

def _load_registry() -> Dict[str, Any]:
    if REG_PATH.exists():
        try:
            return json.loads(REG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_registry(data: Dict[str, Any]):
    REG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _make_training_page(training_name: str) -> str:
    res = notion_client.pages.create(
        parent={"type": 'page_id', "page_id": NOTION_ROOT_PAGE_ID},
        properties={
            "title": {
                "title": [{"type":"text","text":{"content": training_name}}]
            }
        }
    )
    return res["id"]

def _make_child_database(parent_page_id: str) -> str:
    # creating inline DB under the training page
    res = notion_client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type":"text", "text":{"content":"Audio Comments"}}],
        properties = {
            "Name": {"title": {}},
            "Date": {"date": {}},
            "STT_Km": {"rich_text": {}},
            "Translated_En": {"rich_text": {}},
            "Category": {"select": {
                "options": [
                    {"name": "Teacher/Methods", "color": "green"},
                    {"name":"Mass Students","color":"gray"},
                    {"name":"Individual Character","color":"yellow"},
                    {"name":"Individual Evaluation","color":"orange"},
                    {"name":"Individual Verification","color":"purple"},
                    {"name":"Learning of how Student Learn","color":"blue"},
                ]
            }},
            "CategoryConfidence": {"number": {"format":"number"}},
            "AudioURL": {"url": {}},
            "ChatID": {"number": {}},
            "MessageID": {"number": {}},
            "ExternalID": {"rich_text": {}},
        },
        is_inline=True,
    )
    return res["id"]

def ensure_training_space(chat_id: int, training_name: str) -> Tuple[str, str]:
    # chat_id毎に、Notion毎のtraining_idとその中の子DBのIDを保証する
    # すでに同じChatIDがあればそれを返し、なければ新規作成する
    if not NOTION_ROOT_PAGE_ID:
        raise RuntimeError("NOTION_ROOT_PAGE_ID is not set in .env")
    
    reg = _load_registry()
    key = str(chat_id)
    if key in reg and all(k in reg[key] for k in ("training_page_id", "training_db_id")):
        return reg[key]["training_page_id"], reg[key]["training_db_id"]
    
    # create new page & db in the new page
    page_id = _make_training_page(notion_client, training_name)
    db_id = _make_child_database(notion_client, page_id)

    reg[key] = {"training_page_id": page_id, "training_db_id":db_id, "training_name": training_name}
    _save_registry(reg)
    return page_id, db_id