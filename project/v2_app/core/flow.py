from __future__ import annotations
from typing import Any, Dict, List, Optional

Field = Dict[str, Any]

def asked_fields(fields: List[Field]) -> List[Field]:
    return [f for f in fields if f.get("source") == "ask"]

def missing_required(fields: List[Field], filled: Dict[str, Any]) -> List[str]:
    return [
        f["key"] for f in asked_fields(fields) if f.get("required") and not filled.get(f["key"])
    ]

def next_field(fields: List[Field], filled: Dict[str, Any]) -> Optional[Field]:
    for f in asked_fields(fields):
        if f.get("required") and not filled.get(f["key"]):
            return f
    return None

def next_question(fields: List[Field], filled: Dict[str, Any]) -> Optional[str]:
    f = next_field(fields, filled)
    return f["question"] if f else None

def is_complete(fields: List[Field], filled: Dict[str, Any]) -> bool:
    return next_field(fields, filled) is None

def extract_keys(fields: List[Field]) -> List[str]:
    return [f["key"] for f in fields if f.get("source") in ("ask", "ai")]


# Notion
def _to_prop(notion_type: str, value: Any) -> Optional[Dict[str, Any]]:
    if value is None or value == "" or value == []:
        return None

    if notion_type == "title":
        return {"title": [{"type": "text", "text": {"content": str(value)[:2000]}}]}

    if notion_type == "rich_text":
        text = str(value)
        chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)] or [""]
        return {"rich_text": [
            {"type": "text", "text": {"content": c}} for c in chunks
        ]}

    if notion_type == "select":
        return {"select": {"name": str(value)}}

    if notion_type == "multi_select":
        names = value if isinstance(value, list) else [value]
        return {"multi_select": [{"name": str(n)} for n in names if n]}

    if notion_type == "date":
        return {"date": {"start": str(value)}}

    if notion_type == "checkbox":
        return {"checkbox": bool(value)}

    if notion_type == "number":
        return {"number": value}

    if notion_type == "relation":
        ids = value if isinstance(value, list) else [value]
        return {"relation": [{"id": str(i)} for i in ids if i]}

    if notion_type == "files":
        items = value if isinstance(value, list) else [value]
        files = []
        for item in items:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                name, url = item
            else:
                url = item
                name = str(url).rsplit("/", 1)[-1] or "file"
            if url:
                files.append({"name": str(name)[:100],
                              "external": {"url": str(url)}})
        return {"files": files} if files else None

    raise ValueError(f"未対応の notion_type: {notion_type}")


def to_notion_props(fields: List[Field], filled: Dict[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for f in fields:
        prop_name = f.get("notion_prop")
        if not prop_name:
            continue
        built = _to_prop(f["notion_type"], filled.get(f["key"]))
        if built is not None:
            props[prop_name] = built
    return props


# 確認カード
# 確認カードで1項目に出す上限。
#
# ⚠️ もとは120文字で切っていたが、**確認カードは保存前に中身を見る
# 唯一の場所**なので切る理由が無い（2026-10-13変更）。
# 探究テーマは全文が見えないと設定できないし、音声の文字起こしは
# ここでしか先生が内容を確かめられない。
#
# Telegramの1メッセージは4096文字で、telegram._split が分割するので
# 長くても壊れない。それでも暴走を防ぐために上限は置く
CONFIRM_MAX_CHARS = 1500


def render_confirmation(fields: List[Field], filled: Dict[str, Any]) -> str:
    lines = []
    for f in asked_fields(fields):
        v = filled.get(f["key"])
        if not v:
            continue
        label = f.get("label") or f["key"]
        text = str(v)
        if len(text) > CONFIRM_MAX_CHARS:
            text = text[:CONFIRM_MAX_CHARS] + "…"
        lines.append(f"{label}: {text}")
    return "\n".join(lines) if lines else "（まだ何も記録されていません）"
