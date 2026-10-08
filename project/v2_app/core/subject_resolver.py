from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from v2_app.core.config import DB_SUBJECT, MODEL_EXTRACT
from v2_app.core.llm import complete_json
from v2_app.core.notion_client import query_database

SYSTEM = """You match a teacher's words to one subject from a given list.

Rules:
- Choose EXACTLY one name from the list, copied character for character.
- If none of them clearly matches, return null.
- Do NOT invent a name that is not in the list.
"""

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"name": {"type": ["string", "null"]}},
    "required": ["name"],
    "additionalProperties": False,
}

def _plain(s:str) -> str:
    return (s or "").strip().lower().replace(" ","")

def _title_of(page: dict, prop: str) -> str:
    items = page["properties"].get(prop, {}).get("title",[])
    return "".join(i.get("plain_text","") for i in items)

def _text_of(page: dict, prop: str) -> str:
    items = page["properties"].get(prop, {}).get("rich_text", [])
    return "".join(i.get("plain_text", "") for i in items)

async def fetch_candidates(school_page_id: Optional[str]) -> List[Tuple[str,str,str]]:
    """使える教科の一覧を取る。(page_id, Name, Name KM) のリスト。

    キャッシュしない。必要なのは保存時の1回だけなので
    （30人で1日30リクエスト）、毎回取ることでアドミンの追加が即反映される。
    """
    school_filter: Dict[str,Any] = {
        "or": [{"property": "Schools", "relation": {"is_empty": True}}]
    }
    if school_page_id:
        school_filter["or"].append(
            {"property": "Schools", "relation": {"contains": school_page_id}}
        )

    res = await query_database(
        DB_SUBJECT,
        filter={
            "and": [
                {"property": "Is Active", "checkbox": {"equals": True}},
                school_filter,
            ]
        },
        page_size=100,
    )
    return [
        (p["id"], _title_of(p, "Name"), _text_of(p, "Name KM"))
        for p in res.get("results", [])
    ]

async def resolve(
    subject_text: str,
    school_page_id: Optional[str] = None,
    *,
    use_llm: bool = True,
) -> Optional[str]:
    """教科名 → Subject の page id。見つからなければ None。

    Practice Example だけが使う。
    Daily Learning / Lesson Study の教科は自由記述なので照合しない。
    """
    if not subject_text:
        return None

    candidates = await fetch_candidates(school_page_id)

    if not candidates:
        return None

    target = _plain(subject_text)

    #   完全一致
    for page_id, name, name_km in candidates:
        if target in (_plain(name), _plain(name_km)):
            return page_id

    #   部分一致
    for page_id, name, name_km in candidates:
        for cand in (_plain(name), _plain(name_km)):
            if cand and (cand in target or target in cand):
                return page_id

    if not use_llm:
        return None

    # AIに選ばせる
    names = [name for _, name, _ in candidates if name]
    listing = "\n".join(
        f"- {name}" + (f"（{name_km}）" if name_km else "")
        for _, name, name_km in candidates
        if name
    )

    try:
        result = await complete_json(
            SYSTEM,
            f"【候補】\n{listing}\n\n【先生の言葉】\n{subject_text}",
            SCHEMA,
            schema_name="subject_match",
            model=MODEL_EXTRACT,
        )
    except Exception:
        return None

    picked = (result.get("name") or "").strip()
    if not picked or picked not in names:
        return None
    for page_id, name, _ in candidates:
        if name == picked:
            return page_id
    return None