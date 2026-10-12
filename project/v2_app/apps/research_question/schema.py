"""探究テーマ。Notion の Research Question に書く。

RQ が title かつ必須。他のモードと違い、title をAIに作らせない
（先生の問いそのものが記録の中身なので、要約してはいけない）。

Is Current は「今取り組んでいるテーマ」の印。新しく登録したら
既存のものを false にする → handler.before_save
"""

from __future__ import annotations

from typing import Any, Dict, List

from v2_app.core.config import DB_RESEARCH_QUESTION

DB_ID = DB_RESEARCH_QUESTION

FIELDS: List[Dict[str, Any]] = [
    {
        "key": "rq",
        "label": "Research Question",
        "question": "What question do you want to explore in your teaching?",
        "question_km": "តើអ្នកចង់ស្វែងយល់សំណួរអ្វីក្នុងការបង្រៀនរបស់អ្នក?",
        "source": "ask",
        "required": True,
        "notion_prop": "RQ",
        "notion_type": "title",
    },
    {
        "key": "is_current",
        "source": "auto",
        "notion_prop": "Is Current",
        "notion_type": "checkbox",
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
]
