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


@suite.case("非表示のモードは MODES に含まれている（消していない）")
def _() -> None:
    menu_keys = {key for key, _, _ in menu.MODES}
    assert menu.HIDDEN_MODES <= menu_keys, (
        f"MODES に無いものを隠そうとしている: {menu.HIDDEN_MODES - menu_keys}"
    )


@suite.case("visible_modes は非表示を除いたものを返す")
def _() -> None:
    visible = {key for key, _, _ in menu.visible_modes()}
    expected = {key for key, _, _ in menu.MODES} - menu.HIDDEN_MODES
    assert visible == expected, visible


@suite.case("base.handle は保存時に before_save / after_save を渡している")
def _() -> None:
    """渡し忘れるとモード固有の処理が全部動かない（2026-10-13に発生）。

      探究テーマ  Is Current が立たず、マイページも更新されない
      実践例      Subject の照合と Materials のタグが付かない
      授業研究    8分類（Category）が入らない

    どれも**エラーにならず静かに起きる**ので、テストで止める。
    """
    import ast
    import inspect

    from v2_app.apps import base

    tree = ast.parse(inspect.getsource(base.handle))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_save"
    ]
    assert calls, "handle が _save を呼んでいない"
    for call in calls:
        names = {kw.arg for kw in call.keywords}
        for required in ("before_save", "after_save"):
            assert required in names, f"_save に {required} を渡していない"


@suite.case("モード固有の処理を持つモードは base にフックを渡している")
def _() -> None:
    import inspect

    expected = {
        # route → 必要なフック
        "research_question": ("before_save", "after_save"),
        "practice": ("before_save",),
        "lesson_study": ("before_save",),
    }
    for route, hooks in expected.items():
        entry = registry.ROUTES.get(route)
        if not entry or not entry["ready"]:
            continue
        src = inspect.getsource(inspect.getmodule(entry["handler"]))
        for hook in hooks:
            assert f"{hook}=" in src, f"{route} が {hook} を渡していない"
