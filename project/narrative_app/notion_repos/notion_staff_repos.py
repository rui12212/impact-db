from typing import List, Optional, Dict, Any
from core.notion_client import get_notion_client
from core.config import NOTION_STAFF_NARRATIVES_DB_ID

def get_or_create_staff_narrative_for_school(
        school_page_id: str,
) -> str:
    # retrieve the specific record(page) of school from staff_narrative DB
    # if not, create new one and return the ID
    # Staff Narrative DB has School_name property

    notion = get_notion_client()

    # 1 Search existing School Narrative by School_name
    resp = notion.databases.query(
        **{
            "database_id": NOTION_STAFF_NARRATIVES_DB_ID,
            "filter":{
                "property": "School_name",
                "relation": {
                    "contains": school_page_id,
                },
            },
            "page_size": 1,
        }
    )
    results = resp.get("results",[])
    if results:
        return results[0]["id"]
    
    # 2 If there is no school (compared to the school Db), create new one
    create_resp = notion.pages.create(
        **{
            "parent": {"database_id": NOTION_STAFF_NARRATIVES_DB_ID},
            "property": {
                "Name": {
                    "title": [
                        {"text": {"content": "Staff Narrative"}}
                    ]
                },
                "School_name": {
                    "relation": [{"id": school_page_id}]
                },
            },
        }
    )
    return create_resp["id"]

def update_staff_narrative_properties(
        staff_page_id: str,
        school_page_id: Optional[str] = None,
        teacher_page_id: Optional[str] = None,
        subject_page_ids: Optional[List[str]] = None,
        last_practice_at_iso: Optional[str] = None,
        latest_narrative_page_id: Optional[str] = None,
) -> None:
    # Update the propertiers of Starr_Narrative Db
    # -school_page_id: School_name relation
    # - teacher_page_id: teacher_name relation
    # subject_page_ids: Subject Tag (relation), multiple IDs
    # last_practice_at_iso: Last Practice at (date)'s start time
    # latest_narrative_page_id: Latest Narrative (relation)

    # If the Argument is none, the argument will not be updated
    notion = get_notion_client()

    props: Dict[str, Any] = {}

    if school_page_id is not None:
        props["School_name"] = {
            "relation": [{"id": school_page_id}],
        }
    if teacher_page_id is not None:
        props["Teacher_name"] = {
            "relation": [{"id": teacher_page_id}],
        }
    if subject_page_ids is not None:
        props["Subject Tag"] = {
            "relation": [{"id": sid} for sid in subject_page_ids],
        }
    if last_practice_at_iso is not None:
        props["Last Practice At"] = {
            "date": {"start": last_practice_at_iso},
        }
    if latest_narrative_page_id is not None:
        props["Latest Narrative"] = {
            "relation": [{"id": latest_narrative_page_id}],
        }
    if not props:
        return
    
    notion.pages.update(
        **{
            "page_id": staff_page_id,
            "properties": props,
        }
    )