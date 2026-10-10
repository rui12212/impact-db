"""registry と menu の整合。通信なし。

route のキーは文字列なので型では守れない。menu に出ているのに
route が解決できない（またはその逆）事故をここで止める。
"""

from __future__ import annotations

from v2_app.apps import registry
from v2_app.router import menu
from v2_app.tests.harness import Suite

suite = Suite("registry")


@suite.case("menu の MODES と registry の _SPECS のキーが一致する")
def _() -> None:
    menu_keys = {key for key, _, _ in menu.MODES}
    reg_keys = set(registry._SPECS)
    assert menu_keys == reg_keys, f"menu={menu_keys} registry={reg_keys}"


@suite.case("ROUTES には全モードが入っている（未実装でも）")
def _() -> None:
    assert set(registry.ROUTES) == set(registry._SPECS)


@suite.case("get_handler は未知の route で None")
def _() -> None:
    assert registry.get_handler("no_such_mode") is None


@suite.case("どのモードにも呼べる handler がある")
def _() -> None:
    for route, entry in registry.ROUTES.items():
        assert callable(entry["handler"]), route


@suite.case("実装済みのモードには fields と db_id がある")
def _() -> None:
    for route in registry.ready_routes():
        entry = registry.ROUTES[route]
        # settings は対話ではないので fields が空でよい
        if route == "settings":
            continue
        assert entry["fields"], f"{route} に FIELDS がない"
        assert entry["db_id"], f"{route} に DB_ID がない"


@suite.case("実装済みモードの fields は flow が扱える形をしている")
def _() -> None:
    from v2_app.core import flow

    for route in registry.ready_routes():
        fields = registry.ROUTES[route]["fields"]
        for f in fields:
            assert f.get("key"), f"{route}: key がない {f}"
            assert f.get("source"), f'{route}: {f["key"]} に source がない'
            if f.get("notion_prop"):
                assert f.get("notion_type"), (
                    f'{route}: {f["key"]} に notion_type がない'
                )
        # 変換が例外を投げないことだけ見る（値は空なので props は空になる）
        flow.to_notion_props(fields, {})


@suite.case("実装済みモードの key に重複がない")
def _() -> None:
    for route in registry.ready_routes():
        keys = [f["key"] for f in registry.ROUTES[route]["fields"]]
        assert len(keys) == len(set(keys)), f"{route} に重複した key がある"


@suite.case("TEXTS の全キーが en を持っている")
def _() -> None:
    missing = [k for k, v in menu.TEXTS.items() if not v.get("en")]
    assert not missing, f"en が空: {missing}"
