from datetime import datetime, timezone
import logging
from typing import List, Any, Dict, Optional

from core.notion_client import get_notion_client
from narrative_app.notion_repos.subjects_repos import resolve_subject_ids
from narrative_app.summarization import generate_detailed_content, generate_summary
from narrative_app.notion_repos.notion_staff_repos import get_or_create_staff_narrative_for_school,update_staff_narrative_properties

logger = logging.getLogger(__name__)

def _extract_raw_text_from_narrative(page:dict) -> str:
    props = page.get("properties", {})
    rich = props.get("Raw Text", {}).get("rich_text", [])
    return "".join([r.get("plain_text") for r in rich])

def _extract_subject_names_from_narrative(page: dict) -> List[str]:
    # retrieve Subject lists from Subject Tag of Narrative

    props = page.get("properties", {})
    subject_prop = props.get("Subject Tag")

    if not subject_prop:
        return []
    
    if subject_prop.get("select"):
        name = subject_prop["select"].get("name")
        return [name] if name else []

def sync_staff_narrative_from_narrative(narrative_page_id: str) -> None:
    # based on the closed Narrative records, update targeted Staff_narrative_db
    # update Last Practice At, and sort the view based on it
    # Bring schools that have recently implemented the practice to the top

    notion = get_notion_client()

    page = notion.pages.retrieve(narrative_page_id)
    props = page.get("properties", {})

    # Retrieve the relation of School & Teacher
    school_rel = props.get("School", {}).get("relation", [])
    teacher_rel = props.get("Teacher",{}).get("relation",[])
    if not school_rel or not teacher_rel:
        logger.warning(
            "Narrative page %s has no School/Teacher relation. Skipping staff sync.",
            narrative_page_id
        )
        return
    
    # get school_page_id from the related school
    school_page_id = school_rel[0]["id"]
    teacher_page_id = teacher_rel[0]["id"]

    date_prop = props.get("Date",{}).get("date",{}) or {}
    start_str: Optional[str] = date_prop.get("start")
    end_str: Optional[str] = date_prop.get("end") or start_str

    if not end_str:
        # use current time instead
        end_dt = datetime.now(timezone.utc)
        end_iso = end_dt.isoformat().replace("+00:00", "Z")
    else:
        end_iso = end_str
    
    # Retrieve Raw Text / Subject
    raw_text = _extract_raw_text_from_narrative(page)
    subject_names = _extract_subject_names_from_narrative(page)
    subject_page_ids = resolve_subject_ids(subject_names) if subject_names else []
    

    # Retrieve or create new Staff Narrative DB record for the targeted school
    staff_page_id = get_or_create_staff_narrative_for_school(school_page_id)

    update_staff_narrative_properties(
        staff_page_id = staff_page_id,
        school_page_id = school_page_id,
        teacher_page_id = teacher_page_id,
        subject_page_ids = subject_page_ids,
        last_practice_at_iso = end_iso,
        latest_narrative_page_id = narrative_page_id,
    )

    logger.info(
        "Synced staff narrative for school=%s staff_page_id=%s from narrative=%s",
        school_page_id,
        staff_page_id,
        narrative_page_id,
    )

    