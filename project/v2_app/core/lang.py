"""言語コードの扱いを1箇所にまとめる。

→ modify/2026-10-20-japanese-input-language-design.md

**使うのは音声の言語判定の結果を扱うとき。**
`stt.detect_lang()` が返したコードを正規化し、プロンプトに渡す
言語名に変換する。

⚠️ **先生ごとに言語を保存しない**（2026-10-21決定）。

    Telegram の送信メッセージ   英語＋クメール語で**固定**（先方決定 1-16）
    打ち込んだ文               そのまま保存する。言語を見ない
    音声                      **中身から判定する**
    8分類                     何語であれ英訳を渡す
    AIサマリー                 **記録と同じ言語で書く**（先方決定 1-15）

    → どこにも「保存した言語」が要らないので、`User.Language` を持たない。
      持たなくて済むものを持つと、設定画面と運用がそのぶん増える。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

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

def normalize(value: Optional[str]) -> str:
    """'ja-JP' や 'JA' を 'ja' にする。対応外なら空。

    LLMが 'Japanese' や 'ja-JP' のような形で返してくることがあるので、
    判定結果はここを通してから使う。
    """
    if not value:
        return ""

    text = value.strip().lower()

    # 言語名で返ってきた場合（'Khmer' / 'japanese' など）
    for code, english in NAMES.items():
        if text == english.lower():
            return code

    code = text.replace("_", "-").split("-")[0]
    return code if code in SUPPORTED else ""


def name(lang: Optional[str]) -> str:
    """プロンプトに入れる言語名。'Khmer' / 'English' / 'Japanese'"""
    return NAMES.get(normalize(lang) or DEFAULT, NAMES[DEFAULT])


# 文字の範囲で言語を見分ける。
#   クメール文字      U+1780–U+17FF
#   ひらがな          U+3040–U+309F
#   カタカナ          U+30A0–U+30FF
#   漢字（CJK統合）    U+4E00–U+9FFF
_KM = re.compile(r"[ក-៿]")
_JA = re.compile(r"[぀-ゟ゠-ヿ]")
_CJK = re.compile(r"[一-鿿]")


def guess_from_text(text: str) -> str:
    """書かれている文字から言語を見分ける。'km' / 'ja' / 'en'。

    **LLMを使わない。** AIサマリーを「記録と同じ言語」で書くために、
    記録の文字を数えるだけ（2026-10-21決定）。

    ⚠️ ひらがな・カタカナが無い漢字だけの文は中国語と区別できないが、
    この用途では問題にならない（先生は日本語かクメール語か英語で書く）。

    判定できなければ英語とみなす。英語なら英訳のままで出せばよく、
    外した時の害が小さい。
    """
    if not text:
        return "en"

    km = len(_KM.findall(text))
    ja = len(_JA.findall(text)) + len(_CJK.findall(text))

    if km == 0 and ja == 0:
        return "en"
    return "km" if km >= ja else "ja"
