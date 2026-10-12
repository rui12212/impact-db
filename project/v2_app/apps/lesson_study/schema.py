"""授業研究のコメント。Notion の Lesson Study Reflection に書く。

他のモードと違い、会話の前に「どの授業研究へのコメントか」を
一覧から選ばせる段がある → handler.py

Lesson Study ID（unique_id）と4つのロールアップは
APIから書けないので FIELDS に入れない。
"""

from __future__ import annotations

from typing import Any, Dict, List

from v2_app.core.config import DB_LESSON_STUDY_REFLECTION

DB_ID = DB_LESSON_STUDY_REFLECTION

FIELDS: List[Dict[str, Any]] = [
    {
        "key": "comment",
        "label": "Comment",
        "question": "What did you notice in the lesson?",
        "question_km": "តើអ្នកបានកត់សម្គាល់អ្វីក្នុងមេរៀន?",
        "source": "ask",
        "required": True,
        "notion_prop": "Comment",
        "notion_type": "rich_text",
    },
    {
        "key": "summary",
        "label": "Summary",
        "source": "ai",
        "notion_prop": "Summary",
        "notion_type": "title",
    },
    {
        # 8分類。core/categorize.py が入れる
        "key": "category",
        "source": "auto",
        "notion_prop": "Category",
        "notion_type": "select",
    },
    {
        # 一覧から選ばせる。handler が入れる
        "key": "lesson_study",
        "source": "auto",
        "notion_prop": "Lesson Study",
        "notion_type": "relation",
    },
    {
        "key": "stt_km",
        "source": "auto",
        "notion_prop": "STT_Km",
        "notion_type": "rich_text",
    },
    {
        "key": "translated_en",
        "source": "auto",
        "notion_prop": "Translated_En",
        "notion_type": "rich_text",
    },
    {
        # webhookの再送で2件にならないようにする
        "key": "external_id",
        "source": "auto",
        "notion_prop": "ExternalID",
        "notion_type": "rich_text",
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
        "key": "audio",
        "source": "media",
        "media_kind": "voice",
        "notion_prop": "Audio",
        "notion_type": "files",
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
]
