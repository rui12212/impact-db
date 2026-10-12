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
