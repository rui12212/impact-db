"""ElevenLabs Scribe で文字起こしする（2026-11-23追加）。

`stt_gemini.py` と**同じ形（`run()` が (原文, 英訳, "") を返す）**にしてあり、
`core/stt.py` が `V2_STT_PROVIDER` を見てどちらかを選ぶ。

なぜ両方持つのか:
  クメール語には**信頼できる公開ベンチマークが無い。** WER は単語の区切りが
  無い言語で意味を持たず（Whisper-small が FLEURS のクメール語で WER 457%
  という例がある）、商用モデルの比較表はベンダーの自社ページしかない。
  → **自前で測るしかない。** → .claude/topics/v3/transcribe-llm.md

🔴 **英訳は ElevenLabs では行わない。** ElevenLabs は文字起こし専用なので、
英訳は `stt_gemini.translate_to_en` を呼ぶ。**2社にまたがるのは意図的。**
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from v2_app.core import config

# ⚠️ 前処理（ffmpeg）とチャンク分割を stt_gemini から借りている。
# **私的な名前（_ 付き）を他モジュールから使うのは本来よくない。**
# 本筋は core/audio/ 側に移すことだが、いま動かすと ②（言語の強制・
# 30秒チャンク・境界の重複・英訳の短絡）を直した直後のテストが混ざる。
# → **モデルを決めた時に、残った方へ整理する**（V3 の 7番の後片付け）
from v2_app.core.stt_gemini import _cleanup, _prepare, translate_to_en

log = logging.getLogger("impactdb.v2")

# scribe_v3 は 2026-11-10 リリース。
# ⚠️ SDK が知らないIDだとバリデーションで弾かれるので、
# 環境変数で scribe_v1 に下げられるようにしてある（config.py）
MODEL = config.ELEVENLABS_STT_MODEL

_client_cache = None


def _client():
    """SDK のクライアント。**使う時にだけ作る。**

    ⚠️ モジュールの読み込み時に作らない。`V2_STT_PROVIDER=gemini` の
    環境では鍵が無いので、**import するだけで落ちてしまう。**
    """
    global _client_cache
    if _client_cache is None:
        key = os.getenv("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")
        from elevenlabs.client import ElevenLabs

        _client_cache = ElevenLabs(api_key=key)
    return _client_cache


def transcribe(file_path: str, chunks: Optional[List[tuple]] = None) -> str:
    """**話されている言語のまま**文字起こしする。

    🔴 **`language_code` を渡さない**（2026-11-23）。V1 の
    `core/audio/stt_translate.py:331` は `language_code="khm"` を渡していて、
    **Gemini 側で直したのと同じ「言語の強制」**になっている。
    混在音声を測るのが目的なので、自動検出に任せる。

    🔴 **チャンクの設定は stt_gemini と揃える**（5分 / 重複なし）。
    片方だけ 30秒・重複ありにすると**比較が成立しない。**
    `_prepare` を共用しているので自動的に揃う。

    `chunks` を渡せば分割をやり直さない（`_prepare` は重い）。
    """
    parts: List[str] = []
    for chunk_path, _start, _end in (
        chunks if chunks is not None else _prepare(file_path)[0]
    ):
        with open(chunk_path, "rb") as f:
            res = _client().speech_to_text.convert(
                file=f,
                model_id=MODEL,
                diarize=False,
                tag_audio_events=False,
            )
        text = (getattr(res, "text", "") or "").strip()
        if text:
            parts.append(text)

    return "\n".join(parts).strip()


def run(file_path: str) -> tuple:
    """音声 → (原文, 英訳, "")。**`stt_gemini.run` と同じ形。**

    ① ElevenLabs で文字起こし → ② **Gemini で英訳**

    返り値の3番目は常に `""`（言語の判定をしないため。stt_gemini と同じ）。
    同期処理なので、呼ぶ側で別スレッドに逃がす（core/stt.py）。
    """
    chunks, wav = _prepare(file_path)
    try:
        original = transcribe(file_path, chunks=chunks)
        if not original:
            return "", "", ""

        english = translate_to_en(original)
        return original, english, ""
    finally:
        # ⚠️ **必ず消す。** 消さないと5分の音声1本で約20MB残る
        _cleanup(chunks, wav)
