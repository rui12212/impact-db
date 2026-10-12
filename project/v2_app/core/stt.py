from __future__ import annotations

import asyncio
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

    return (km or "").strip(), (en or "").strip()


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
