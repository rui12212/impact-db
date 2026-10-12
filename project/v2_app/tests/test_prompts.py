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


@suite.case("format_history の役割ラベルは英語")
def _() -> None:
    # ラベルに日本語を使うとモデルがそれを真似て日本語で返す
    # → post-deploy/llm-tuning.md §2-0
    text = extract.format_history(
        [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
    )
    assert text == "Teacher: x\nBot: y", repr(text)


@suite.case("format_history: 空なら (none)")
def _() -> None:
    assert extract.format_history([]) == "(none)"


@suite.case("_describe_fields は ask 項目のキーとラベルを並べる")
def _() -> None:
    text = extract._describe_fields(DAILY_FIELDS)
    assert "- note: Reflection (How was your lesson today?)" in text, text
    # ai / auto / media は抽出対象ではないので出てこない
    assert "summary" not in text
    assert "image" not in text


@suite.case("追い質問は固定文を1回だけ（2026-10-13変更）")
def _() -> None:
    # もとはLLMに掘り下げさせていたが、実機でくどかった。
    # 「他にありますか」を1回だけ固定文で聞く
    assert ask.MAX_FOLLOWUP == 1
    assert ask.FOLLOWUP_EN
    assert ask.FOLLOWUP_KM


@suite.case("履歴の上限とキーワード数の定数がある")
def _() -> None:
    assert extract.HISTORY_LAST_N > 0
    assert summarize.MAX_KEYWORDS > 0


@suite.case("プロンプトに日本語が混ざっていない")
def _() -> None:
    """モデルに渡す文字列に日本語があると、それを真似て日本語で返す。

    実際に起きた不具合 → post-deploy/llm-tuning.md §2-0
    docstring・コメント・ログは日本語でよいが、プロンプトはダメ。
    """
    import ast
    import inspect
    import re

    from v2_app.core import ask, categorize, extract, subject_resolver, summarize

    # ひらがな・カタカナ・全角記号。漢字は見ない（固有名詞と衝突するため）
    JA = re.compile(r"[\u3040-\u30ff【】（）、。：]")

    bad = []
    for mod in (ask, extract, summarize, subject_resolver, categorize):
        tree = ast.parse(inspect.getsource(mod))

        # 1パス目: 見なくてよい文字列の id を集める
        skip = set()
        for node in ast.walk(tree):
            # docstring（Expr に包まれた文字列）
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                skip.add(id(node.value))
            # log.warning("...") のような呼び出しの中身すべて
            func = getattr(node, "func", None)
            if (
                isinstance(node, ast.Call)
                and isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "log"
            ):
                for sub in ast.walk(node):
                    skip.add(id(sub))

        # 2パス目: 残った文字列を見る
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in skip:
                continue
            if JA.search(node.value):
                bad.append(f"{mod.__name__}: {node.value[:40]!r}")

    assert not bad, "プロンプトに日本語:\n  " + "\n  ".join(bad)
