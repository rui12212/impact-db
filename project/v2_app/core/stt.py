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


def main_text(km: str, en: str) -> str:
    """抽出・分類に渡す本文を選ぶ。

    extract.py と categorizer は英語で動かせる（英訳があるので）。
    英訳が取れなかった時だけクメール語をそのまま渡す。
    """
    return en or km
