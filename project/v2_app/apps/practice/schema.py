"""実践例。Notion の Practice Example に書く。

必須は Aim / Content / Reflection の3つ（guide §7-3）。
Subject だけ2つのプロパティに入る:
  Subject Text  先生の言葉をそのまま（rich_text）
  Subject       教科マスタと照合できた時だけ（relation）
→ v2-implementation-guide.md §4
"""

from __future__ import annotations

from typing import Any, Dict, List

from v2_app.core.config import DB_PRACTICE_EXAMPLE

DB_ID = DB_PRACTICE_EXAMPLE

FIELDS: List[Dict[str, Any]] = [
    {
        "key": "aim",
        "label": "Aim",
        "question": "What are you trying to achieve with this practice?",
        "question_km": "តើអ្នកចង់សម្រេចអ្វីជាមួយការអនុវត្តនេះ?",
        "source": "ask",
        "required": True,
        "notion_prop": "Aim",
        "notion_type": "rich_text",
    },
    {
        "key": "content",
        "label": "Content",
        "question": "What will you actually do in the lesson?",
        "question_km": "តើអ្នកនឹងធ្វើអ្វីពិតប្រាកដក្នុងមេរៀន?",
        "source": "ask",
        "required": True,
        "notion_prop": "Content",
        "notion_type": "rich_text",
    },
    {
        "key": "reflection",
        "label": "Reflection",
        "question": "How did it go when you tried it?",
        "question_km": "តើវាដំណើរការយ៉ាងណានៅពេលអ្នកសាកល្បង?",
        "source": "ask",
        "required": True,
        "notion_prop": "Reflection",
        "notion_type": "rich_text",
    },
    {
        "key": "subject_text",
        "label": "Subject",
        "question": "Which subject is this for?",
        "question_km": "តើនេះសម្រាប់មុខវិជ្ជាអ្វី?",
        "source": "ask",
        "required": False,
        "notion_prop": "Subject Text",
        "notion_type": "rich_text",
    },
    {
        "key": "grade",
        "label": "Grade",
        "question": "Which grade?",
        "question_km": "ថ្នាក់ទីប៉ុន្មាន?",
        "source": "ask",
        "required": False,
        "notion_prop": "Grade",
        "notion_type": "rich_text",
    },
    {
        "key": "title",
        "label": "Title",
        "source": "ai",
        "notion_prop": "Title",
        "notion_type": "title",
    },
    {
        # subject_text を教科マスタと照合した結果。handler が入れる
        "key": "subject",
        "source": "auto",
        "notion_prop": "Subject",
        "notion_type": "relation",
    },
    {
        # 添付されたメディアの種類からタグを付ける。handler が入れる
        "key": "materials",
        "source": "auto",
        "notion_prop": "Materials",
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

# Materials の選択肢。添付されたメディアから自動で付ける
MATERIAL_BY_KIND = {
    "photo": "Photo",
    "video": "Video",
    "voice": "Audio",
    "document": "Document",
}
