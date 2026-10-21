"""文字起こしの後処理。通信なし。

V1の経路をそのまま使っているので、本文に2種類のノイズが混ざる。
V1のコードはV1本番と共用なので触らず、V2側で落としている。
"""

from __future__ import annotations

from v2_app.core import stt, stt_gemini
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


# ------------------------------------------------ Gemini のクライアントの扱い

class _FakeModels:
    def __init__(self, fail_times: int) -> None:
        self.calls = 0
        self.fail_times = fail_times

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        return "ok"


class _FakeClient:
    def __init__(self, fail_times: int = 0) -> None:
        self.models = _FakeModels(fail_times)


@suite.case("クライアントは使い回す（毎回作ると2回目が落ちる）")
def _() -> None:
    """⚠️ 毎回 genai.Client() を作ると
    「client has been closed」で落ちる（2026-10-22に実機で発生）。
    1件の音声で何回も呼ぶので、使い回しが前提。
    """
    stt_gemini._client_cache = _FakeClient()
    try:
        assert stt_gemini._client() is stt_gemini._client()
    finally:
        stt_gemini._client_cache = None


@suite.case("閉じられていたら作り直して1回だけやり直す")
def _() -> None:
    """⚠️ 使い回しの弱点。一度閉じられると、作り直さない限り
    **プロセスを再起動するまで全部の音声が失敗する。**
    """
    made = []
    real = stt_gemini._client

    def fake_client():
        if stt_gemini._client_cache is None:
            made.append(1)
            stt_gemini._client_cache = _FakeClient()
        return stt_gemini._client_cache

    stt_gemini._client_cache = _FakeClient(fail_times=1)
    stt_gemini._client = fake_client
    try:
        assert stt_gemini._generate(model="x", contents=["y"]) == "ok"
        assert made == [1], "作り直していない"
    finally:
        stt_gemini._client = real
        stt_gemini._client_cache = None


@suite.case("やり直しは1回だけ（無駄に使用量を増やさない）")
def _() -> None:
    real = stt_gemini._client

    def fake_client():
        if stt_gemini._client_cache is None:
            stt_gemini._client_cache = _FakeClient(fail_times=9)
        return stt_gemini._client_cache

    stt_gemini._client_cache = _FakeClient(fail_times=9)
    stt_gemini._client = fake_client
    try:
        raised = False
        try:
            stt_gemini._generate(model="x", contents=["y"])
        except RuntimeError:
            raised = True
        assert raised, "ずっと落ちているのに例外を返していない"
    finally:
        stt_gemini._client = real
        stt_gemini._client_cache = None


@suite.case("閉じられ以外のエラーはそのまま投げる")
def _() -> None:
    """⚠️ 何でもやり直すと、本当に落ちている時に使用量だけ増える。"""
    class _Boom:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise ValueError("quota exceeded")

    stt_gemini._client_cache = _Boom()
    try:
        raised = ""
        try:
            stt_gemini._generate(model="x", contents=["y"])
        except ValueError as e:
            raised = str(e)
        assert raised == "quota exceeded", raised
    finally:
        stt_gemini._client_cache = None
