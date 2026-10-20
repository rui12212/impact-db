"""base.py の小さな関数。通信なし。

会話ループ本体は実機で見るしかないが、文字を切る判断だけは
「消してはいけない文を消す」事故につながるのでここで止める。
"""

from __future__ import annotations

from v2_app.apps import base
from v2_app.tests.harness import Suite

suite = Suite("base")

LONG = "ក" * 400


@suite.case("短い文はそのまま返す")
def _() -> None:
    assert base._clip("short", {"stt_km": LONG}) == "short"


@suite.case("STT_Km に全文があれば切って「…」を付ける")
def _() -> None:
    out = base._clip(LONG, {"stt_km": LONG})
    assert out.endswith(base.ELLIPSIS), out
    assert len(out) == base.VERBATIM_MAX + 1, len(out)


@suite.case("STT_Km が無いときは切らない")
def _() -> None:
    """打ち込まれた文はそこにしか無い。切ると消える。"""
    assert base._clip(LONG, {}) == LONG
    assert base._clip(LONG, {"stt_km": ""}) == LONG


@suite.case("ちょうど上限なら切らない")
def _() -> None:
    text = "a" * base.VERBATIM_MAX
    assert base._clip(text, {"stt_km": text}) == text


@suite.case("1回目はそのまま入る")
def _() -> None:
    assert base._appended(None, "I used group work.") == "I used group work."
    assert base._appended("", "I used group work.") == "I used group work."


@suite.case("2回目は空行を挟んで足される（上書きしない）")
def _() -> None:
    """⚠️ ここが Add more の本体。上書きすると先生の発話が消える。"""
    out = base._appended("I used group work.", "Two quiet boys explained.")
    assert out == "I used group work.\n\nTwo quiet boys explained."


@suite.case("3回繰り返しても全部残る")
def _() -> None:
    out = ""
    for part in ("one", "two", "three"):
        out = base._appended(out, part)
    assert out == "one\n\ntwo\n\nthree", out


@suite.case("空の発話は足さない（写真だけ送られた時）")
def _() -> None:
    assert base._appended("one", "") == "one"
    assert base._appended("one", "   ") == "one"


@suite.case("クメール語を壊さない")
def _() -> None:
    km1, km2 = "ខ្ញុំបានប្រើការងារក្រុម", "សិស្សបានពន្យល់"
    assert base._appended(km1, km2) == f"{km1}\n\n{km2}"


@suite.case("授業研究だけが STT_Km を持つ（切る対象が限られる）")
def _() -> None:
    """⚠️ 他のモードに stt_km を足すと、そのモードの文も切られ始める。

    探究テーマは use_llm=False で同じ経路を通るが、stt_km を
    持たないので切られない。足す時はここを思い出す。
    """
    from v2_app.apps import registry

    has = {
        route
        for route in registry.ready_routes()
        if any(f["key"] == "stt_km" for f in registry.ROUTES[route]["fields"])
    }
    assert has == {"lesson_study"}, has
