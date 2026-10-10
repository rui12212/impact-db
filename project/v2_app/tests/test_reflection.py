"""日々の振り返りの schema。通信なし。

プロパティ名の打ち間違いを Notion に行く前に止める。
期待値は scripts/notion_db_verify.py の EXPECTED["daily_learning"] と同じ。
"""

from __future__ import annotations

from v2_app.apps import reflection
from v2_app.core import flow
from v2_app.tests.harness import Suite

suite = Suite("reflection")

# Notion の実物。Learning ID は unique_id なので Bot は書かない
EXPECTED_PROPS = {
    "Summary",
    "Note",
    "Subject",
    "Keywords",
    "Date",
    "Teacher",
    "School",
    "Image",
    "Video",
    "Audio",
    "Files",
}


@suite.case("書き込むプロパティ名が Notion の実物と一致する")
def _() -> None:
    props = {
        f["notion_prop"] for f in reflection.FIELDS if f.get("notion_prop")
    }
    assert props == EXPECTED_PROPS, (
        f"余分: {props - EXPECTED_PROPS}  足りない: {EXPECTED_PROPS - props}"
    )


@suite.case("unique_id の Learning ID を書こうとしていない")
def _() -> None:
    # APIからは書けないので、入れると validation_error になる
    props = {f.get("notion_prop") for f in reflection.FIELDS}
    assert "Learning ID" not in props


@suite.case("必須は Note だけ")
def _() -> None:
    required = [f["key"] for f in flow.asked_fields(reflection.FIELDS) if f.get("required")]
    assert required == ["note"], required


@suite.case("先生が答える項目には question がある")
def _() -> None:
    for f in flow.asked_fields(reflection.FIELDS):
        assert f.get("question"), f'{f["key"]} に question がない'


@suite.case("media 項目には media_kind がある（振り分けに必要）")
def _() -> None:
    kinds = {}
    for f in reflection.FIELDS:
        if f.get("source") != "media":
            continue
        kind = f.get("media_kind")
        assert kind, f'{f["key"]} に media_kind がない'
        assert kind not in kinds, f"media_kind={kind} が重複している"
        kinds[kind] = f["key"]
    assert set(kinds) == {"photo", "video", "voice", "document"}, kinds


@suite.case("本文だけで Notion に書ける形になる")
def _() -> None:
    filled = {
        "note": "Today I taught fractions to grade 5.",
        "summary": "Fractions in grade 5",
        "date": "2026-10-10",
        "teacher": "page-teacher",
        "school": "page-school",
    }
    props = flow.to_notion_props(reflection.FIELDS, filled)
    assert set(props) == {"Note", "Summary", "Date", "Teacher", "School"}, set(props)
    assert props["Note"]["rich_text"][0]["text"]["content"] == filled["note"]
    assert props["Teacher"]["relation"] == [{"id": "page-teacher"}]


@suite.case("メディアのURLは files プロパティになる")
def _() -> None:
    url = "https://cdn.example.com/impact/reflection/202610/photo_1_ab12cd34.jpg"
    props = flow.to_notion_props(reflection.FIELDS, {"note": "x", "image": [url]})
    assert props["Image"]["files"] == [
        {"name": "photo_1_ab12cd34.jpg", "external": {"url": url}}
    ]


@suite.case("handler は reflection の route を使う")
def _() -> None:
    from v2_app.apps.reflection import handler

    assert handler.ROUTE == "reflection"


@suite.case("DB_ID が設定されている")
def _() -> None:
    assert reflection.DB_ID, "NOTION_V2_DAILY_LEARNING_DB_ID が空"
