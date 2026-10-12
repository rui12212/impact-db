from __future__ import annotations

import asyncio
import re
import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("impactdb.v2")

# V1の core/audio をそのまま使う（2026-10-09決定）。
# 前処理とチャンク化の必要性は10月中に検証する
# → .claude/todo/v2-stt-preprocess-verification.md
PROVIDER = "gemini"


def pick_audio(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Telegram のメッセージから音声を取り出す。無ければ None。

    voice（音声メッセージ）/ audio（音楽ファイル）/ document（音声の添付）
    の3経路に対応する。返り値に file_id と mime_type が入る。
    """
    from core.audio.helpers_audio import pick_audio_from_message

    return pick_audio_from_message(msg)


# V1の transcribe_gemini_km が付けてくるタイムスタンプ。
# 30秒ごとに分割して "[00:00.000-00:30.000] 本文" の形で連結している
_TIMESTAMP = re.compile(r"\[\s*\d{1,2}:\d{2}(?:[.:]\d+)?\s*-\s*\d{1,2}:\d{2}(?:[.:]\d+)?\s*\]")

# LLMが本文の前に付ける前置き。コロンで終わり、文字起こしや言語に
# 言及している部分を落とす。
#   "The audio content is in English, not Khmer. Here is the verbatim
#    transcription in English:"
_PREAMBLE_WORDS = (
    "transcription", "transcript", "audio", "language",
    "khmer", "english", "verbatim", "here is", "note",
)

# 前置きを探す範囲。本文の途中のコロンを誤って切らないため
_PREAMBLE_LIMIT = 300


def _strip_preamble(text: str) -> str:
    """LLMが付けた前置きを落とす。

    最初のコロンまでを見て、文字起こしや言語について語っていれば捨てる。
    本文中のコロン（"9:30 に始めた" など）を誤って切らないよう、
    範囲を頭 _PREAMBLE_LIMIT 文字に限り、キーワードで判定する。
    """
    head = text[:_PREAMBLE_LIMIT]
    for sep in (":", "："):
        idx = head.rfind(sep)
        if idx < 0:
            continue
        candidate = head[:idx].lower()
        if any(w in candidate for w in _PREAMBLE_WORDS):
            return text[idx + 1 :].lstrip()
    return text


def clean_transcript(text: str) -> str:
    """文字起こしから、本文以外を落とす。

    ⚠️ V1の経路をそのまま使っているので、本文に2種類のノイズが混ざる
    （2026-10-13に実機で発覚）。V1のコードはV1本番と共用なので触らず、
    V2側で落とす。

      1. タイムスタンプ  "[00:00-00:08] ..."
      2. LLMの前置き     "The audio content is in English, not Khmer.
                          Here is the verbatim transcription in English:"

    → 根本の解決は T-1（STTの検証）で前処理とチャンク化を見直す時
    """
    if not text:
        return ""
    text = _TIMESTAMP.sub(" ", text)
    text = _strip_preamble(text)
    # 空行と行頭行末の空白を整える
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


async def transcribe(file_path: str) -> Tuple[str, str]:
    """音声ファイル → (クメール語の文字起こし, 英訳)。

    V1の decide_transcribe_model をそのまま呼ぶ。中は同期処理
    （ffmpeg・numpy・requests）なので、別スレッドに逃がして
    イベントループを止めない。

    失敗したら ("", "") を返す。音声が1件取れなくても
    対話そのものは続けられるようにする。
    """
    from core.audio.stt_translate import decide_transcribe_model

    try:
        km, en = await asyncio.to_thread(
            decide_transcribe_model, file_path, PROVIDER
        )
    except Exception as e:
        log.warning("transcribe failed: %s", e)
        return "", ""

    return clean_transcript(km), clean_transcript(en)


async def detect_lang(file_path: str) -> str:
    """音声の言語を判定する。'km' / 'en' など。

    guide §7-1 の言語判定。Botが返す言葉をどちらにするかに使う。
    """
    from core.audio.stt_translate import detect_language

    try:
        return await asyncio.to_thread(detect_language, file_path, PROVIDER)
    except Exception as e:
        log.warning("detect_language failed: %s", e)
        return ""


def teacher_text(km: str, en: str) -> str:
    """**先生自身の言葉**を返す。クメール語を優先する。

    会話履歴・問いかけの生成・Notionの本文に使う。

    ⚠️ ここで英訳を優先すると実害が2つ出る（2026-10-13に実機で発生）
      1. history に英語が積まれ、ask.py が「この先生は英語で書いている」と
         判断してクメール語の先生に英語で返す
      2. Notion の Note に英訳が入る。先生自身の言葉が残らない
    """
    return km or en


def analysis_text(km: str, en: str) -> str:
    """**英訳**を返す。英訳が無ければクメール語。

    コメントの8分類（core/categorize.py）に使う。V1の categorizer が
    英語の例文を埋め込んでいるので、英語で渡さないと精度が落ちる。

    抽出（extract.py）には使わない。Note に先生の言葉を残すため。
    """
    return en or km
