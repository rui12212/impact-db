"""flow.py のテスト。通信なし。"""

from __future__ import annotations

from v2_app.core import flow
from v2_app.tests.fixtures import DAILY_FIELDS
from v2_app.tests.harness import Suite

suite = Suite("flow")


@suite.case("asked_fields は source=ask だけを返す")
def _() -> None:
    keys = [f["key"] for f in flow.asked_fields(DAILY_FIELDS)]
    assert keys == ["note", "subject", "scratch"], keys


@suite.case("extract_keys は ask と ai を返す（auto/media は含まない）")
def _() -> None:
    keys = flow.extract_keys(DAILY_FIELDS)
    assert keys == ["note", "subject", "summary", "keywords", "scratch"], keys


@suite.case("空なら必須項目が未充足")
def _() -> None:
    assert flow.missing_required(DAILY_FIELDS, {}) == ["note"]
    assert not flow.is_complete(DAILY_FIELDS, {})


@suite.case("必須が埋まれば完了（任意は空でよい）")
def _() -> None:
    filled = {"note": "算数で分数をやった"}
    assert flow.missing_required(DAILY_FIELDS, filled) == []
    assert flow.is_complete(DAILY_FIELDS, filled)
    assert flow.next_field(DAILY_FIELDS, filled) is None
    assert flow.next_question(DAILY_FIELDS, filled) is None


@suite.case("next_question は最初の未充足な必須項目の質問")
def _() -> None:
    q = flow.next_question(DAILY_FIELDS, {})
    assert q == "How was your lesson today?", q


@suite.case("空文字は未充足として扱う")
def _() -> None:
    assert flow.missing_required(DAILY_FIELDS, {"note": ""}) == ["note"]


@suite.case("to_notion_props: notion_prop が無い項目は送らない")
def _() -> None:
    props = flow.to_notion_props(DAILY_FIELDS, {"note": "a", "scratch": "b"})
    assert set(props) == {"Note"}, props


@suite.case("to_notion_props: 空の値はプロパティごと省く")
def _() -> None:
    props = flow.to_notion_props(
        DAILY_FIELDS,
        {"note": "a", "subject": "", "keywords": [], "image": None, "date": None},
    )
    assert set(props) == {"Note"}, props


@suite.case("rich_text は2000文字ごとに分割される")
def _() -> None:
    long_text = "あ" * 4500
    prop = flow._to_prop("rich_text", long_text)
    chunks = prop["rich_text"]
    assert len(chunks) == 3, len(chunks)
    assert [len(c["text"]["content"]) for c in chunks] == [2000, 2000, 500]
    assert "".join(c["text"]["content"] for c in chunks) == long_text


@suite.case("title は2000文字で切り捨てる（分割できないので）")
def _() -> None:
    prop = flow._to_prop("title", "A" * 3000)
    assert len(prop["title"]) == 1
    assert len(prop["title"][0]["text"]["content"]) == 2000


@suite.case("multi_select は単体でもリストでも受ける。空要素は落とす")
def _() -> None:
    assert flow._to_prop("multi_select", "分数") == {
        "multi_select": [{"name": "分数"}]
    }
    names = [m["name"] for m in flow._to_prop("multi_select", ["a", "", "b"])["multi_select"]]
    assert names == ["a", "b"], names


@suite.case("relation は id のリストになる")
def _() -> None:
    assert flow._to_prop("relation", "page-1") == {"relation": [{"id": "page-1"}]}
    assert flow._to_prop("relation", ["p1", "p2"])["relation"] == [
        {"id": "p1"},
        {"id": "p2"},
    ]


@suite.case("files: URLだけ渡すと末尾が表示名になる（media.py の命名と合う）")
def _() -> None:
    url = "https://cdn.example.com/impact/reflection/202610/photo_123_ab12cd34.jpg"
    prop = flow._to_prop("files", [url])
    assert prop["files"] == [
        {"name": "photo_123_ab12cd34.jpg", "external": {"url": url}}
    ], prop


@suite.case("files: (name, url) のタプルも受ける")
def _() -> None:
    prop = flow._to_prop("files", [("写真", "https://x/y.jpg")])
    assert prop["files"][0]["name"] == "写真"


@suite.case("files: 表示名は100文字で切る")
def _() -> None:
    prop = flow._to_prop("files", [("あ" * 300, "https://x/y.jpg")])
    assert len(prop["files"][0]["name"]) == 100


@suite.case("checkbox / number / date")
def _() -> None:
    assert flow._to_prop("checkbox", True) == {"checkbox": True}
    assert flow._to_prop("number", 3) == {"number": 3}
    assert flow._to_prop("date", "2026-10-06") == {"date": {"start": "2026-10-06"}}


@suite.case("checkbox の False は省かれずに送られる")
def _() -> None:
    # 空判定は None / "" / [] だけなので False と 0 は通る。
    # Research Question の Is Current=false を消せる必要があるのでこれが正しい。
    assert flow._to_prop("checkbox", False) == {"checkbox": False}
    assert flow._to_prop("number", 0) == {"number": 0}


@suite.case("未対応の型は ValueError")
def _() -> None:
    try:
        flow._to_prop("people", "x")
    except ValueError:
        return
    raise AssertionError("ValueError が出なかった")


@suite.case("render_confirmation は埋まっている ask 項目だけ出す")
def _() -> None:
    text = flow.render_confirmation(DAILY_FIELDS, {"note": "fractions", "summary": "x"})
    assert text == "Reflection: fractions", repr(text)


@suite.case("render_confirmation は長文もそのまま出す（200文字は切らない）")
def _() -> None:
    # 確認カードは保存前に中身を見る唯一の場所。切らない
    note = "あ" * 200
    text = flow.render_confirmation(DAILY_FIELDS, {"note": note})
    assert note in text
    assert not text.endswith("…")


@suite.case("render_confirmation は上限を超えたら省略する")
def _() -> None:
    text = flow.render_confirmation(
        DAILY_FIELDS, {"note": "あ" * (flow.CONFIRM_MAX_CHARS + 100)}
    )
    assert text.endswith("…")
    assert len(text) == len("Reflection: ") + flow.CONFIRM_MAX_CHARS + 1


@suite.case("render_confirmation: 何も無ければ案内文")
def _() -> None:
    assert flow.render_confirmation(DAILY_FIELDS, {}) == "（まだ何も記録されていません）"
