from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from v2_app.core.config import SESSION_TTL_SECONDS
from v2_app.core.redis_client import get_redis

TTL = SESSION_TTL_SECONDS

def _route_key(telegram_id: int) -> str:
    return f"route:{telegram_id}"

def _session_key(app: str, telegram_id: int) -> str:
    return f"{app}:session:{telegram_id}"

def _history_key(app: str, telegram_id:int) -> str:
    return f"{app}:history:{telegram_id}"

def _user_key(telegram_id:int) -> str:
    return f"user:{telegram_id}"

# route
def get_route(telegram_id: int) -> Optional[str]:
    return get_redis().get(_route_key(telegram_id))

def set_route(telegram_id:int, app:str) -> None:
    get_redis().set(_route_key(telegram_id), app, ex=TTL)

def clear_route(telegram_id: int) -> None:
    get_redis().delete(_route_key(telegram_id))

# session
def new_session(app:str, telegram_id:int, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    session = {
        "filled": {f["key"]: None for f in fields},
        "started_at": datetime.now(timezone.utc).isoformat(),
        'ask_count': 0,
    }
    _save_session(app, telegram_id, session)
    set_route(telegram_id,app)
    return session

def get_session(app: str, telegram_id: int) -> Optional[Dict[str, Any]]:
    row= get_redis().get(
        _session_key(app, telegram_id)
    )
    return json.loads(row) if row else None

def _save_session(app:str, telegram_id: int, session:Dict[str, Any]) -> None:
    get_redis().set(
        _session_key(app, telegram_id),
        json.dumps(session, ensure_ascii=False),
        ex=TTL,
    )

def update_filled(app: str, telegram_id:int, values:Dict[str,Any]) -> Optional[Dict[str, Any]]:
    session = get_session(app, telegram_id)
    if session is None:
        return None
    for k, v in values.items():
        if v is None:
            continue
        if k not in session["filled"]:
            continue
        session['filled'][k] = v
    _save_session(app, telegram_id, session)
    return session["filled"]

def bump_ask_count(app:str, telegram_id:int) -> int:
    session = get_session(app, telegram_id)
    if session is None:
        return 0
    session["ask_count"] = int(session.get("ask_count",0)) +1
    _save_session(app, telegram_id, session)
    return session["ask_count"]

def clear_session(app: str, telegram_id:int) -> None:
    get_redis().delete(
        _session_key(app, telegram_id),
        _history_key(app, telegram_id),
        _route_key(telegram_id),
    )

# history
def append_history(app: str, telegram_id:int, role:str, content: str) -> None:
    r = get_redis()
    key = _history_key(app, telegram_id)
    r.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    r.expire(key, TTL)
    r.expire(_route_key(telegram_id), TTL) 

def get_history(app: str, telegram_id:int, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
    start = -last_n if last_n else 0
    raw = get_redis().lrange(_history_key(app, telegram_id), start, -1)
    return [json.loads(x) for x in raw]

# user
def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    raw = get_redis().get(_user_key(telegram_id))
    return json.loads(raw) if raw else None

def set_user(telegram_id:int, data: Dict[str, Any]) -> None:
    get_redis().set(_user_key(telegram_id), json.dumps(data, ensure_ascii=False))

def get_lang(telegram_id:int) -> Optional[str]:
    user = get_user(telegram_id)
    return user.get("lang") if user else None

def set_lang(telegram_id: int, lang:str) -> None:
    user = get_user(telegram_id) or {}
    user["lang"] = lang
    set_user(telegram_id, user)

def clear_user(telegram_id: int) -> None:
    get_redis().delete(_user_key(telegram_id))
    



    