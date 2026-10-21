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
    """音声ファイル → (原文の文字起こし, 英訳)。

    ⚠️ **原文はクメール語に限らない**（2026-10-21変更）。
    `core/stt_gemini.py` が音声の言語を判定し、その言語で起こす。
    日本語の音声なら日本語が返る。

    V1の decide_transcribe_model は使わない。あれは
    プロンプトに `(Khmer)` と決め打ちしていて、日本語で結果が
    保証できない（V1本番と共用なので触らない）。

    中は同期処理（ffmpeg・Gemini）なので別スレッドに逃がして
    イベントループを止めない。

    失敗したら ("", "") を返す。音声が1件取れなくても
    対話そのものは続けられるようにする。
    """
    original, english, _code = await transcribe_with_lang(file_path)
    return original, english


async def transcribe_with_lang(file_path: str) -> Tuple[str, str, str]:
    """音声ファイル → (原文, 英訳, 判定した言語)。

    言語も知りたい呼び出し側のため（Botの返事を何語にするか等）。
    """
    from v2_app.core import stt_gemini

    try:
        original, english, code = await asyncio.to_thread(
            stt_gemini.run, file_path
        )
    except Exception as e:
        log.warning("transcribe failed: %s", e)
        return "", "", ""

    return clean_transcript(original), clean_transcript(english), code


async def detect_lang(file_path: str) -> str:
    """音声の言語を判定する。'km' / 'en' / 'ja'。

    ⚠️ V1の detect_language は使わない。**'km' と 'en' しか返さず、
    日本語を 'km' に丸める**（stt_translate.py:456）。

    ⚠️ 通常は transcribe_with_lang を使う。あちらは判定の結果を
    文字起こしにも使い回すので、Geminiの呼び出しが1回少ない。
    """
    from v2_app.core import stt_gemini

    try:
        return await asyncio.to_thread(stt_gemini.detect_lang, file_path)
    except Exception as e:
        log.warning("detect_lang failed: %s", e)
        return ""


def teacher_text(km: str, en: str) -> str:
    """**先生自身の言葉**を返す。原文を優先する。

    ⚠️ 引数名の `km` は**原文**という意味（2026-10-21）。
    日本語の音声なら日本語が入る。Notionのプロパティ名
    （`STT_Km`）と揃えるために名前を変えていない。

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
