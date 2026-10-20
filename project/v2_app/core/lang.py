"""先生の言語をどう決めるかを1箇所にまとめる。

→ modify/2026-10-20-japanese-input-language-design.md

**打ち込み（テキスト）**

    ① 設定で選んだ言語        Notion の User.Language（Redis にキャッシュ）
    ② Telegram の言語コード    初回接触時に入る（router/dispatcher.py）
    ③ 既定                    km

**音声**

    ① 音声の中身をLLMが判定   ← これだけ。ここは使わない（stt.detect_lang）

⚠️ **音声で端末の設定を見ない理由。** 端末の表示言語と、実際に話す言語は
   一致しない。英語設定の端末で日本語を話す組み合わせが普通に起きる。
   打ち込みは本人が選んだ言語で書くので設定で足りるが、音声は中身を
   聞かないと分からない（2026-10-20決定）。

⚠️ 選んだ言語は **Notion が正本**。Redis だけに持つとコンテナを止めた時に
   消える（2026-10-20決定）。
"""

from __future__ import annotations

import logging
from typing import Optional

from v2_app.core import session

log = logging.getLogger("impactdb.v2")

# 対応する言語。ここに無いものは既定に落とす
SUPPORTED = ("km", "en", "ja")
DEFAULT = "km"

# プロンプトに渡す言語名。LLMには英語で指示する
NAMES = {
    "km": "Khmer",
    "en": "English",
    "ja": "Japanese",
}

# 設定の画面に出す名前。先生自身が読む
LABELS = {
    "km": "ភាសាខ្មែរ (Khmer)",
    "en": "English",
    "ja": "日本語 (Japanese)",
}


def normalize(value: Optional[str]) -> str:
    """'ja-JP' や 'JA' を 'ja' にする。対応外なら空。

    Telegram の言語コードは 'en-US' のような形で来ることがある。
    """
    if not value:
        return ""
    code = value.strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED else ""


def for_text(telegram_id: int) -> str:
    """打ち込みの時に使う言語。必ず SUPPORTED のどれかを返す。"""
    chosen = normalize(session.get_lang_choice(telegram_id))
    if chosen:
        return chosen

    from_device = normalize(session.get_lang(telegram_id))
    if from_device:
        return from_device

    return DEFAULT


def name(lang: Optional[str]) -> str:
    """プロンプトに入れる言語名。'Khmer' / 'English' / 'Japanese'"""
    return NAMES.get(normalize(lang) or DEFAULT, NAMES[DEFAULT])


def label(lang: Optional[str]) -> str:
    """設定の画面に出す名前。"""
    return LABELS.get(normalize(lang) or DEFAULT, LABELS[DEFAULT])
