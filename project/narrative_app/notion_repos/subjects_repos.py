from typing import List

from core.notion_client import get_notion_client
from core.config import NOTION_SUBJECTS_DB_ID

def get_or_create_subject_by_name(name: str) -> str:
    # retrieve Subject name page ID If no, create new page id, and return it
    # Subjects DB has to have a Name(title) property
    notion = get_notion_client()

    # 1 search existing Subject
    resp = notion.databases.query(
        **{
            "database_id": NOTION_SUBJECTS_DB_ID,
            "filter": {
                "property": "Name",
                "title": {
                    "equals":name,
                },
            },
            "page_size": 1,
        }
    )

    results = resp.get("results", [])
    if results:
        return results[0]["id"]
    
    # 2 If there  is no, create new
    create_resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_SUBJECTS_DB_ID},
            "properties": {
                "Name": {
                    "title": [
                        {"text": {"content": name}}
                    ]
                }
            },
        }
    )
    return create_resp["id"]

def resolve_subject_ids(subject_names: List[str]) -> List[str]:
    # This helper returns each Subject DB page ID from multiple subjects'name
    # if name is no exist on Subject DB, auto create new one
    # return page id list
    ids: List[str] = []
    for name in subject_names:
        name = (name or "").strip()
        if not name:
            continue
        page_id = get_or_create_subject_by_name(name)
        ids.append(page_id)
    return ids

