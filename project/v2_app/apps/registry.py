from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, List, Optional

from v2_app.core import telegram

log = logging.getLogger("impactdb.v2")

Handler = Callable[..., Any]

# route キー → パッケージ名。
# キーは router/menu.py の MODES と一致させる（テストで確認している）
_SPECS: Dict[str, str] = {
    "reflection": "v2_app.apps.reflection",
    "practice": "v2_app.apps.practice",
    "lesson_study": "v2_app.apps.lesson_study",
    "research_question": "v2_app.apps.research_question",
    "settings": "v2_app.apps.settings",
}

NOT_READY_EN = "This is not available yet."
NOT_READY_KM = "មុខងារនេះមិនអាចប្រើបានទេនៅពេលនេះ។"


def _not_ready_text() -> str:
    return f"{NOT_READY_EN}\n{NOT_READY_KM}" if NOT_READY_KM else NOT_READY_EN


def _placeholder(route: str) -> Handler:
    """まだ作っていないモードの受け皿。

    1本ずつ作っていくので、未実装でもBotは起動して他のモードは動く。
    選ばれたらセッションを捨てて、使えないことだけ伝える。
    """

    async def handle(inc: Any, user: Dict[str, Any]) -> None:
        from v2_app.core import session

        log.info("未実装のモードが選ばれた route=%s", route)
        session.clear_session(route, inc.telegram_id)
        await telegram.send_message(inc.chat_id, _not_ready_text())

    return handle


def _load() -> Dict[str, Dict[str, Any]]:
    """各モードを読み込む。読めないものは placeholder に差し替える。

    ⚠️ 書きかけの handler に構文エラーがあってもBot全体を落とさない。
    落とすと、動いているモードまで止まって原因が分かりにくくなる。
    """
    routes: Dict[str, Dict[str, Any]] = {}

    for route, module_path in _SPECS.items():
        entry: Dict[str, Any] = {
            "fields": [],
            "handler": _placeholder(route),
            "db_id": "",
            "ready": False,
        }

        try:
            mod = importlib.import_module(module_path)
        except ModuleNotFoundError:
            log.info("未実装のモード route=%s", route)
            routes[route] = entry
            continue
        except Exception:
            log.exception("モードの読み込みに失敗 route=%s", route)
            routes[route] = entry
            continue

        handler = getattr(mod, "handle", None)
        if handler is None:
            log.warning("%s に handle がない", module_path)
            routes[route] = entry
            continue

        entry.update(
            fields=getattr(mod, "FIELDS", []),
            handler=handler,
            db_id=getattr(mod, "DB_ID", ""),
            ready=True,
        )
        routes[route] = entry

    return routes


ROUTES: Dict[str, Dict[str, Any]] = _load()


def get_handler(route: str) -> Optional[Handler]:
    """dispatcher が使う。未知の route なら None。"""
    entry = ROUTES.get(route)
    return entry["handler"] if entry else None


def ready_routes() -> List[str]:
    """実装済みのモード。/healthz や起動ログで確認する用。"""
    return [route for route, entry in ROUTES.items() if entry["ready"]]
