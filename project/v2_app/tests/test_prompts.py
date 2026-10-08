"""LLMに渡す「組み立て部分」だけのテスト。APIは呼ばない。"""

from __future__ import annotations

from v2_app.core import ask, extract, summarize
from v2_app.core.llm import build_object_schema
from v2_app.tests.fixtures import DAILY_FIELDS
from v2_app.tests.harness import Suite

suite = Suite("prompts (API呼び出しなし)")


@suite.case("build_object_schema は strict mode の形を満たす")
def _() -> None:
    schema = build_object_schema(["note", "subject"])
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    # strict mode は全キーが required でなければならない
    assert set(schema["required"]) == set(schema["properties"]) == {"note", "subject"}


@suite.case("スキーマの各キーは string か null を取れる（未回答を表せる）")
def _() -> None:
    schema = build_object_schema(["note"])
    assert schema["properties"]["note"]["type"] == ["string", "null"]


@suite.case("format_history は役割を日本語ラベルにする")
def _() -> None:
    text = extract.format_history(
        [{"role": "user", "content": "分数"}, {"role": "assistant", "content": "なぜ？"}]
    )
    assert text == "先生: 分数\nBot: なぜ？", repr(text)


@suite.case("format_history: 空なら「(なし)」")
def _() -> None:
    assert extract.format_history([]) == "(なし)"


@suite.case("_describe_fields は ask 項目のキーとラベルを並べる")
def _() -> None:
    text = extract._describe_fields(DAILY_FIELDS)
    assert "- note: 振り返り（今日の授業はどうでしたか？）" in text, text
    # ai / auto / media は抽出対象ではないので出てこない
    assert "summary" not in text
    assert "image" not in text


@suite.case("追い質問の上限は 2 回（案C）")
def _() -> None:
    assert ask.MAX_FOLLOWUP == 2


@suite.case("履歴の上限とキーワード数の定数がある")
def _() -> None:
    assert extract.HISTORY_LAST_N > 0
    assert summarize.MAX_KEYWORDS > 0
