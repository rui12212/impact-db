"""全モードの schema を Notion の設計と突き合わせる。通信なし。

正本は scripts/notion_db_verify.py の EXPECTED（Notionの実物を検証する
のに使っている辞書）。schema.py のプロパティ名・型の打ち間違いを
Notionに行く前に止める。

実装済みのモードを registry から取るので、モードを足せば自動で対象になる。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from v2_app.apps import registry
from v2_app.tests.harness import Suite

suite = Suite("schemas (全モード)")

# scripts/ はパッケージではないのでパスを通して読む
_SCRIPTS = Path("/app/project/v2_app/scripts")
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import notion_db_verify as verify  # noqa: E402

# route → EXPECTED のキー
DB_KEY = {
    "reflection": "daily_learning",
    "practice": "practice_example",
    "research_question": "research_question",
    "lesson_study": "lesson_study_reflection",
}

# APIから書けないので schema に入れてはいけない型
UNWRITABLE = ("unique_id", "rollup", "formula", "created_time", "last_edited_time")


def _expected(route: str) -> Dict[str, Any]:
    return verify.EXPECTED[DB_KEY[route]]


def _type_of(spec: Any) -> str:
    """EXPECTED の値は "rich_text" か ("relation", "user") の形。"""
    return spec[0] if isinstance(spec, tuple) else spec


def _targets():
    """検証する対象。settings は Notion DB に直接書かないので除く。"""
    return [r for r in registry.ready_routes() if r in DB_KEY]


@suite.case("検証対象のモードが1つ以上ある")
def _() -> None:
    assert _targets(), "実装済みのモードが無い"


@suite.case("書き込むプロパティが全部 Notion に存在する")
def _() -> None:
    for route in _targets():
        expected = _expected(route)
        for f in registry.ROUTES[route]["fields"]:
            prop = f.get("notion_prop")
            if not prop:
                continue
            assert prop in expected, (
                f"{route}: Notion に無いプロパティ {prop!r}"
                f"（{DB_KEY[route]} の候補: {sorted(expected)}）"
            )


@suite.case("notion_type が Notion の型と一致する")
def _() -> None:
    for route in _targets():
        expected = _expected(route)
        for f in registry.ROUTES[route]["fields"]:
            prop = f.get("notion_prop")
            if not prop:
                continue
            want = _type_of(expected[prop])
            got = f["notion_type"]
            assert got == want, f"{route}.{prop}: schema={got} Notion={want}"


@suite.case("APIから書けない型（unique_id / rollup など）を書こうとしていない")
def _() -> None:
    for route in _targets():
        expected = _expected(route)
        for f in registry.ROUTES[route]["fields"]:
            prop = f.get("notion_prop")
            if not prop:
                continue
            want = _type_of(expected[prop])
            assert want not in UNWRITABLE, (
                f"{route}: {prop} は {want} なので API から書けない"
            )


@suite.case("Teacher / School / Date をどのモードも自動で埋めている")
def _() -> None:
    for route in _targets():
        keys = {
            f["notion_prop"]: f
            for f in registry.ROUTES[route]["fields"]
            if f.get("notion_prop")
        }
        for prop in ("Teacher", "School", "Date"):
            assert prop in keys, f"{route}: {prop} が schema に無い"
            assert keys[prop]["source"] == "auto", (
                f"{route}: {prop} は auto であるべき"
            )


@suite.case("title のプロパティが1つだけある")
def _() -> None:
    for route in _targets():
        titles = [
            f["key"]
            for f in registry.ROUTES[route]["fields"]
            if f.get("notion_type") == "title"
        ]
        assert len(titles) == 1, f"{route}: title が {len(titles)}個 {titles}"


@suite.case("必須項目が1つ以上ある")
def _() -> None:
    for route in _targets():
        required = [
            f["key"]
            for f in registry.ROUTES[route]["fields"]
            if f.get("source") == "ask" and f.get("required")
        ]
        assert required, f"{route}: 必須項目が無い。1往復で保存できてしまう"


@suite.case("base が自動で入れる key は、持つモードでは型が揃っている")
def _() -> None:
    # base._save が入れる値と notion_type の対応
    want = {
        "date": "date",
        "teacher": "relation",
        "school": "relation",
        "external_id": "rich_text",
        "summary": "title",
        "title": "title",
        "keywords": "multi_select",
    }
    for route in _targets():
        for f in registry.ROUTES[route]["fields"]:
            key = f["key"]
            if key in want:
                assert f["notion_type"] == want[key], (
                    f'{route}.{key}: base は {want[key]} を入れるが '
                    f'schema は {f["notion_type"]}'
                )
