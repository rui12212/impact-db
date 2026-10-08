"""テスト用のダミー fields。実物（Daily Learning）に近い形にしてある。"""

from __future__ import annotations

from typing import Any, Dict, List

Field = Dict[str, Any]

DAILY_FIELDS: List[Field] = [
    {
        "key": "note",
        "label": "振り返り",
        "question": "今日の授業はどうでしたか？",
        "source": "ask",
        "required": True,
        "notion_prop": "Note",
        "notion_type": "rich_text",
    },
    {
        "key": "subject",
        "label": "教科",
        "question": "何の教科でしたか？",
        "source": "ask",
        "required": False,
        "notion_prop": "Subject",
        "notion_type": "rich_text",
    },
    {
        "key": "summary",
        "label": "見出し",
        "source": "ai",
        "notion_prop": "Summary",
        "notion_type": "title",
    },
    {
        "key": "keywords",
        "label": "キーワード",
        "source": "ai",
        "notion_prop": "Keywords",
        "notion_type": "multi_select",
    },
    {
        "key": "date",
        "source": "auto",
        "notion_prop": "Date",
        "notion_type": "date",
    },
    {
        "key": "teacher",
        "source": "auto",
        "notion_prop": "Teacher",
        "notion_type": "relation",
    },
    {
        "key": "image",
        "source": "media",
        "notion_prop": "Image",
        "notion_type": "files",
    },
    {
        # notion_prop を持たない項目は Notion に送られない
        "key": "scratch",
        "source": "ask",
        "required": False,
        "question": "（内部用）",
        "notion_type": "rich_text",
    },
]

# テストで使う telegram_id。実運用のIDとぶつからない負の値にする
TEST_TELEGRAM_ID = -999001
TEST_APP = "pytest_app"
