import os, json,logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from core.notion_client import get_notion_client
from dotenv import load_dotenv
load_dotenv()
from typing import Any, Dict, Optional,List, Tuple


REG_PATH = Path(".runtime/chat_registry.json")
REG_PATH.parent.mkdir(parents=True, exist_ok=True)
NOTION_ROOT_PAGE_ID = os.getenv("NOTION_ROOT_PAGE_ID")

notion = get_notion_client()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

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
    res = notion.pages.create(
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
    res = notion.databases.create(
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
    page_id = _make_training_page(training_name)
    db_id = _make_child_database(page_id)

    reg[key] = {"training_page_id": page_id, "training_db_id":db_id, "training_name": training_name}
    _save_registry(reg)
    return page_id, db_id

# Notion Helper
def chunk(text:str, size:int=1000) -> List[str]:
    return [text[i:i+size] for i in range(0, len(text), size)] or [""]


def page_exists_by_external_id(database_id: str, external_id:str) -> Optional[str]:
    # external_id(rich_text)が一致するページがあればそのIDを返す
    try:
        res = notion.databases.query(
            **{
                'database_id': database_id,
                'filter': {'property':'ExternalID', 'rich_text':{'equals':external_id}},
                'page_size': 1
            }
        )
        results = res.get('results', [])
        return results[0]['id'] if results else None
    except Exception as e:
        log.warning(f"Notion query failed: {e}")
        return None

def create_or_update_notion_page(
        db_id: str, properties:Dict[str,Any], transcript_km: str, transcript_en:str, extra_children:Optional[List[Dict[str,Any]]] =None
)-> str:
    # 先にExternalIDがあれば更新、なければ作成
    external_id = ''.join([
        t['text']['content']
        for t in properties['ExternalID']['rich_text']
    ]) if 'ExternalID' in properties else None

    page_id = page_exists_by_external_id(db_id, external_id) if external_id else None

    children = []
    if transcript_km:
        children.append({
            'object': 'block', 'type': 'heading_2',
            'heading_2': {'rich_text': [{'type':'text','text':{'content': 'Transcript (KM)'}}]}
        })
    
    if transcript_en:
        children.append({
            "object":"block","type":"heading_2",
            "heading_2":{"rich_text":[{"type":"text","text":{"content":"Translation (EN)"}}]}
        })
        for part in chunk(transcript_en):
            children.append({
                "object":"block","type":"paragraph",
                "paragraph":{"rich_text":[{"type":"text","text":{"content":part}}]}
            })
    # Evidenceなどを後ろに連結
    if extra_children:
        children.extend(extra_children)
    
    if page_id:
         notion.pages.update(page_id=page_id, properties=properties)
         return page_id
    else:
        res = notion.pages.create(
            parent={'database_id': db_id},
            properties=properties,
            children=children
        )
        return res['id']