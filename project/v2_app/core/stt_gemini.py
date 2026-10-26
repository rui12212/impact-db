"""音声の言語判定・文字起こし・英訳。V2側で持つ。

→ modify/2026-10-20-japanese-input-language-design.md

**なぜ V1 を使わないか。** V1（`core/audio/stt_translate.py`）は
クメール語を決め打ちしている。

    :369  "...verbatim in the language spoken (Khmer)."
    :404  detect_language は 'km' / 'en' しか返さず、**日本語は km に丸める**
    :385  translate_gemini_km_to_en はクメール語→英語で固定

日本語に対応するには直す必要があるが、**V1 は本番と共用しているので
触らない**。ここは V2 専用の経路として作り、V1 からは
「音声の前処理」「チャンク分割」「使用量カウント」だけを借りる。

⚠️ **タイムスタンプを付けない。** V1は `[00:00-00:30]` を付けるので
   `stt.clean_transcript` が正規表現で落としていた。付けて落とすより
   最初から付けないほうが確実（本文中のコロンを誤って切る危険も消える）。
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import List, Optional, Tuple

from v2_app.core import lang as lang_mod

log = logging.getLogger("impactdb.v2")

MODEL = "gemini-2.5-flash"

# 1チャンクの長さ。V1と同じ
CHUNK_MS = 30_000
OVERLAP_MS = 1_500

DETECT_PROMPT = (
    "Listen to this audio and identify the language. "
    "Reply with ONLY one of these codes and nothing else: "
    "'km' for Khmer/Cambodian, 'en' for English, 'ja' for Japanese. "
    "If you are unsure, reply 'km'."
)


_client_cache = None


def _client():
    """Gemini のクライアント。**1つ作って使い回す。**

    ⚠️ 毎回 `genai.Client()` を作ると、2回目以降が
    **`Cannot send a request, as the client has been closed`** で落ちる
    （2026-10-22に実機で発生）。SDKが内部のHTTPクライアントを共有して
    いるため、前のクライアントが回収されると共有分まで閉じられる。

    1件の音声で判定1回＋チャンクごとの文字起こし＋英訳と**何回も呼ぶ**
    ので、ここは必ず使い回す。
    """
    global _client_cache

    if _client_cache is not None:
        return _client_cache

    from google import genai

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    _client_cache = genai.Client(api_key=key)
    return _client_cache


# クライアントが閉じられた時にSDKが出す文字列
_CLOSED = "client has been closed"


def _generate(**kwargs):
    """Gemini を呼ぶ。**閉じられていたら作り直して1回だけやり直す。**

    ⚠️ 使い回しの弱点を埋める。一度閉じられると、作り直さない限り
    **以降すべての音声が失敗し、プロセスを再起動するまで直らない。**
    ここで拾えば先生からは何も起きていないように見える。

    やり直しは1回だけ。何度も繰り返すと、本当に落ちている時に
    Geminiの使用量だけが増える。
    """
    global _client_cache

    try:
        return _client().models.generate_content(**kwargs)
    except Exception as e:
        if _CLOSED not in str(e):
            raise
        log.warning("Geminiのクライアントが閉じられていた。作り直して再試行")
        _client_cache = None
        return _client().models.generate_content(**kwargs)


def _prepare(file_path: str) -> Tuple[List[tuple], str]:
    """音声を wav にして30秒ごとに切る。**V1の部品をそのまま借りる。**

    返すのは (チャンク, 前処理後のwavのパス)。wav のパスも返すのは
    **あとで消すため**（→ `_cleanup`）。

    ⚠️ **重い。** 中では音声全体に対してノイズ低減・バンドパス・EQ・
    正規化・VAD が走る。1件の音声につき**1回だけ**呼ぶこと
    （2026-10-26まで detect_lang と transcribe が別々に呼んでいて、
    同じ処理が2回走っていた）
    """
    from core.audio.audio_preprocess import preprocess_for_stt
    from core.audio.stt_chunking import split_wav_to_chunks

    wav = preprocess_for_stt(file_path)
    chunks = split_wav_to_chunks(wav, chunk_ms=CHUNK_MS, overlap_ms=OVERLAP_MS)
    return chunks, wav


def _chunks(file_path: str) -> List[tuple]:
    """チャンクだけ欲しい時の入口。**後片付けができないので run では使わない。**"""
    chunks, _wav = _prepare(file_path)
    return chunks


def _cleanup(chunks: List[tuple], wav: str = "") -> None:
    """一時ファイルを消す。

    ⚠️ **V1 の部品は一時ファイルを消さない。** `split_wav_to_chunks` は
    チャンクごとに `mkdtemp()` し、`preprocess_for_stt` も `mkdtemp()` する。
    消さないと**5分の音声1本で約20MBがコンテナに残り続ける**。
    `/tmp` は再起動で消えるので、デプロイ頻度に救われていた。

    ⚠️ **1つだけ消せないものが残る。** `preprocess_for_stt` が内部で作る
    16kHz変換後の wav（`_to_wav16k_mono` の出力）はパスが返ってこない。
    消すには V1 の `audio_preprocess.py` を直す必要があるため見送った
    （V1本番と共用）。

    失敗しても例外にしない。後片付けで記録を落とさない。
    """
    paths = [c[0] for c in chunks]
    if wav:
        paths.append(wav)

    for path in paths:
        try:
            shutil.rmtree(os.path.dirname(path), ignore_errors=True)
        except Exception:
            log.warning("一時ファイルを消せなかった: %s", path)


def _quota() -> None:
    """Gemini の使用量を数える。**V1と同じカウンタを使う**（月の上限を共有）。"""
    from core.gemini_quota import check_and_increment

    check_and_increment()


def detect_lang(file_path: str, chunks: Optional[List[tuple]] = None) -> str:
    """音声の言語。'km' / 'en' / 'ja'。判定できなければ既定（km）。

    **最初のチャンクだけ**を聞く。全部聞く必要が無く、呼び出しも増える。

    `chunks` を渡せば分割をやり直さない。**`_prepare` は重いので、
    run() のように続けて transcribe も呼ぶ場合は必ず渡す。**
    """
    chunks = chunks if chunks is not None else _chunks(file_path)
    if not chunks:
        log.warning("チャンクが作れないので言語は既定にする")
        return lang_mod.DEFAULT

    first_path = chunks[0][0]
    _quota()

    with open(first_path, "rb") as f:
        audio = f.read()

    res = _generate(
        model=MODEL,
        contents=[
            DETECT_PROMPT,
            {"inline_data": {"data": audio, "mime_type": "audio/wav"}},
        ],
    )

    # ⚠️ 'Japanese' や 'ja-JP' で返ってくることがあるので正規化を通す
    code = lang_mod.normalize(getattr(res, "text", ""))
    if not code:
        log.warning("言語を判定できなかった: %r", getattr(res, "text", "")[:40])
        return lang_mod.DEFAULT

    log.info("音声の言語: %s", code)
    return code


def transcribe(
    file_path: str, code: str, chunks: Optional[List[tuple]] = None
) -> str:
    """判定した言語で文字起こしする。

    ⚠️ **言語を決め打ちしない。** V1は `(Khmer)` と書いていたので、
    日本語の音声で結果が保証できなかった。

    `chunks` を渡せば分割をやり直さない（→ `detect_lang`）。
    """
    language = lang_mod.name(code)
    prompt = (
        f"Please transcribe the content of this audio verbatim in {language}. "
        "Translation is not required. "
        "Output ONLY the transcription. "
        "Do not add timestamps, headings, notes or any preamble."
    )

    parts: List[str] = []
    for chunk_path, _start, _end in (
        chunks if chunks is not None else _chunks(file_path)
    ):
        _quota()
        with open(chunk_path, "rb") as f:
            audio = f.read()

        res = _generate(
            model=MODEL,
            contents=[
                prompt,
                {"inline_data": {"data": audio, "mime_type": "audio/wav"}},
            ],
        )
        text = (getattr(res, "text", "") or "").strip()
        if text:
            parts.append(text)

    return "\n".join(parts).strip()


def translate_to_en(text: str, code: Optional[str] = None) -> str:
    """英訳する。8分類が英語を要求するため（core/categorize.py）。

    ⚠️ **英語の音声では呼ばない**（2026-10-21決定）。既に英語なので
    Gemini を1回節約できる。呼び出し側で判断する。
    """
    if not text.strip():
        return ""
    if lang_mod.normalize(code) == "en":
        return text

    from google.genai import types

    _quota()
    res = _generate(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a professional interpreter. Translate the given text "
                "into accurate, natural English. "
                "Output ONLY the translation, with no preamble."
            ),
        ),
        contents=[text],
    )
    return (getattr(res, "text", "") or "").strip()


def run(file_path: str) -> tuple:
    """音声 → (原文, 英訳, 判定した言語)。

    ① 言語を判定 → ② その言語で文字起こし → ③ 英訳

    Gemini の呼び出し回数は **1（判定）＋チャンク数（文字起こし）＋1（英訳）**。
    30秒ごとに切るので、音声が長いほど増える（5分で13回）。
    同期処理なので、呼ぶ側で別スレッドに逃がす（core/stt.py）。

    ⚠️ **前処理と分割は1回だけ**（2026-10-26変更）。以前は detect_lang と
    transcribe がそれぞれ `_chunks()` を呼んでいたので、**重いDSP処理が
    2回走り、一時ファイルも2倍残っていた**。
    """
    chunks, wav = _prepare(file_path)
    try:
        code = detect_lang(file_path, chunks=chunks)
        original = transcribe(file_path, code, chunks=chunks)
        if not original:
            return "", "", code

        english = translate_to_en(original, code)
        return original, english, code
    finally:
        # ⚠️ **必ず消す。** 消さないと5分の音声1本で約20MB残る
        _cleanup(chunks, wav)
