"""日々の振り返り。Notion の Daily Learning に書く。

必須は Note だけ。教科は聞くが任意（proposal §4-6）。
プロパティ名は Notion の実物と完全一致させる
→ v2-implementation-guide.md §4
"""

from __future__ import annotations

from typing import Any, Dict, List

from v2_app.core.config import DB_DAILY_LEARNING

DB_ID = DB_DAILY_LEARNING

FIELDS: List[Dict[str, Any]] = [
    {
        "key": "note",
        "label": "Reflection",
        "question": "What is your learning today?",
        # 仮訳（開発側）。先方への確認は A-9 の便で
        "question_km": "តើថ្ងៃនេះអ្នកបានរៀនអ្វី?",
        "source": "ask",
        "required": True,
        "notion_prop": "Note",
        "notion_type": "rich_text",
    },
    {
        "key": "subject",
        "label": "Subject",
        "question": "Which subject was it?",
        "question_km": "តើវាជាមុខវិជ្ជាអ្វី?",
        "source": "ask",
        "required": False,
        "notion_prop": "Subject",
        "notion_type": "rich_text",
    },
    {
        # title は必須なので、AIが作れなくても make_summary が何か返す
        "key": "summary",
        "label": "Summary",
        "source": "ai",
        "notion_prop": "Summary",
        "notion_type": "title",
    },
    {
        "key": "keywords",
        "label": "Keywords",
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
        "key": "school",
        "source": "auto",
        "notion_prop": "School",
        "notion_type": "relation",
    },
    {
        "key": "image",
        "source": "media",
        "media_kind": "photo",
        "notion_prop": "Image",
        "notion_type": "files",
    },
    {
        "key": "video",
        "source": "media",
        "media_kind": "video",
        "notion_prop": "Video",
        "notion_type": "files",
    },
    {
        "key": "audio",
        "source": "media",
        "media_kind": "voice",
        "notion_prop": "Audio",
        "notion_type": "files",
    },
    {
        "key": "files",
        "source": "media",
        "media_kind": "document",
        "notion_prop": "Files",
        "notion_type": "files",
    },
]
