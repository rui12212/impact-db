"""文字起こしの後処理。通信なし。

V1の経路をそのまま使っているので、本文に2種類のノイズが混ざる。
V1のコードはV1本番と共用なので触らず、V2側で落としている。
"""

from __future__ import annotations

from v2_app.core import stt
from v2_app.tests.harness import Suite

suite = Suite("stt (後処理)")


@suite.case("タイムスタンプを落とす")
def _() -> None:
    text = "[00:00.000-00:30.000] hello\n[00:30.000-01:00.000] world"
    assert stt.clean_transcript(text) == "hello\nworld"


@suite.case("LLMの前置きを落とす")
def _() -> None:
    text = (
        "[00:00-00:08] The audio content is in English, not Khmer. "
        "Here is the verbatim transcription in English:\n\n"
        "How teachers can facilitate kids learning."
    )
    assert stt.clean_transcript(text) == "How teachers can facilitate kids learning."


@suite.case("本文中のコロンは切らない")
def _() -> None:
    # これを切ってしまうと先生の記録が消える
    text = "We started at 9:30 and the kids were focused."
    assert stt.clean_transcript(text) == text


@suite.case("日付や時刻だけの行を壊さない")
def _() -> None:
    text = "The class ran 8:15 to 9:00. Two students were late."
    assert stt.clean_transcript(text) == text


@suite.case("クメール語の本文を壊さない")
def _() -> None:
    text = "ថ្ងៃនេះខ្ញុំបានបង្រៀនប្រភាគ។ សិស្សមានការផ្តោតល្អ។"
    assert stt.clean_transcript(text) == text


@suite.case("空なら空を返す")
def _() -> None:
    assert stt.clean_transcript("") == ""
    assert stt.clean_transcript("   \n  ") == ""


@suite.case("teacher_text はクメール語を優先する")
def _() -> None:
    # ここで英訳を優先すると history が英語になり、
    # クメール語の先生に英語で返る（2026-10-13に発生）
    assert stt.teacher_text("km", "en") == "km"
    assert stt.teacher_text("", "en") == "en"


@suite.case("analysis_text は英訳を優先する")
def _() -> None:
    # 8分類は V1 の categorizer が英語の例文を埋め込んでいる
    assert stt.analysis_text("km", "en") == "en"
    assert stt.analysis_text("km", "") == "km"
