"""授業研究のコメント。Notion の Lesson Study Reflection に書く。

他のモードと違い、会話の前に「どの授業研究へのコメントか」を
一覧から選ばせる段がある → handler.py

⚠️ **文字情報は入力手段で分ける**（2026-10-26変更）
   → modify/2026-10-26-lesson-study-text-audio-restructure.md

     Comment_org    打ち込み＋音声＋caption の原文（**全部ここに入る**）
     Text_org       そのうち打ち込み＋caption だけ
     Audio_stt_org  そのうち音声の文字起こしだけ
     Comment_eng    Comment_org の英訳（カテゴライズの入力）

   以前は言語で分けていた（原文=STT_Km / 英訳=Translated_En）。
   旧プロパティは Notion に残るが**ここから外したので書き込まれない**
   （flow.to_notion_props は FIELDS からプロパティを組み立てる）。
   過去のレコードの値はそのまま残る。

⚠️ **`required` は comment_org に置く。** `summarize._main_text` が
   「source=ask かつ required」の項目を本文として Summary と Slack に渡すので、
   **打ち込みだけの text_org に移すと音声だけの記録で本文が空になる。**

Lesson Study Reflection ID（unique_id）と4つのロールアップは
APIから書けないので FIELDS に入れない。
"""

from __future__ import annotations

from typing import Any, Dict, List

from v2_app.core.config import DB_LESSON_STUDY_REFLECTION

DB_ID = DB_LESSON_STUDY_REFLECTION

FIELDS: List[Dict[str, Any]] = [
    {
        # 打ち込み・音声・caption が**全部ここに積まれる**（accumulate の宛先）
        "key": "comment_org",
        "label": "Comment",
        "question": "What did you learn through the learning of students today?",
        # 仮訳（開発側）。先方への確認は A-9 の便で
        "question_km": "តើថ្ងៃនេះអ្នកបានរៀនអ្វីពីការរៀនសូត្ររបស់សិស្ស?",
        "source": "ask",
        "required": True,
        "notion_prop": "Comment_org",
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
        # 打ち込みと caption だけ。base.py が accumulate と並行して積む
        "key": "text_org",
        "source": "auto",
        "notion_prop": "Text_org",
        "notion_type": "rich_text",
    },
    {
        # 音声の文字起こしだけ。原文（クメール語・日本語・英語）のまま
        "key": "audio_stt_org",
        "source": "auto",
        "notion_prop": "Audio_stt_org",
        "notion_type": "rich_text",
    },
    {
        # comment_org の英訳。handler の before_save が保存の直前に作る。
        # **カテゴライズの入力**なので、要約や言い換えが入らないようにする
        "key": "comment_eng",
        "source": "auto",
        "notion_prop": "Comment_eng",
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
