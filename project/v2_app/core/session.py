from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from v2_app.core.config import SESSION_TTL_SECONDS
from v2_app.core.redis_client import get_redis

TTL = SESSION_TTL_SECONDS
APPS = ("reflection", "practice", "lesson_study", "research_question", "settings")


def _route_key(telegram_id: int) -> str:
    return f"route:{telegram_id}"

def _session_key(app: str, telegram_id: int) -> str:
    return f"{app}:session:{telegram_id}"

def _history_key(app: str, telegram_id:int) -> str:
    return f"{app}:history:{telegram_id}"

def _user_key(telegram_id:int) -> str:
    return f"user:{telegram_id}"

def _pending_key(app: str, telegram_id: int) -> str:
    return f"{app}:pending:{telegram_id}"

def _notice_key(app: str, telegram_id: int) -> str:
    return f"{app}:notice:{telegram_id}"

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
        _pending_key(app, telegram_id),
        _notice_key(app, telegram_id),
        _route_key(telegram_id),
    )

def clear_all_sessions(telegram_id: int) -> None:
    """入力中のデータを全モード分捨てる（proposal §4-7 A案）。

    route を上書きするだけでは前のモードの session と history が
    3日間残る。モードを選んだら必ず白紙から始めるために回す。
    user:{telegram_id} は対象外（所属・言語は消さない）。
    """
    for app in APPS:
        clear_session(app, telegram_id)

# pending: 次に来るメッセージが何の入力かを覚えておく。
# settings モードが使う（名前の入力待ちなど）。
# filled に混ぜると Notion のプロパティと紛らわしいので別キーにする。
def get_pending(app: str, telegram_id: int) -> str:
    """何の入力を待っているか。待っていなければ空文字。"""
    return get_redis().get(_pending_key(app, telegram_id)) or ""

def set_pending(app: str, telegram_id: int, value: str) -> None:
    """入力待ちにする。空文字を渡すと解除する。

    update_filled では解除できない（None を無視する作りなので）。
    """
    key = _pending_key(app, telegram_id)
    if not value:
        get_redis().delete(key)
        return
    get_redis().set(key, value, ex=TTL)

# notice: 出している「Thinking...」の message_id を覚えておく。
# 写真を複数枚送るとTelegramが1枚ずつ別メッセージで送ってくるので、
# 覚えておかないと Thinking が枚数分出る
NOTICE_TTL = 600

def get_notice(app: str, telegram_id: int) -> Optional[int]:
    """いま出している Thinking の message_id。無ければ None。"""
    raw = get_redis().get(_notice_key(app, telegram_id))
    return int(raw) if raw else None

def set_notice(app: str, telegram_id: int, message_id: int) -> None:
    get_redis().set(_notice_key(app, telegram_id), str(message_id), ex=NOTICE_TTL)

def clear_notice(app: str, telegram_id: int) -> None:
    get_redis().delete(_notice_key(app, telegram_id))

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


def acquire_lock(name: str, telegram_id: int, ttl: int = 60) -> bool:
    """鍵を取る。取れたら True、既に誰かが持っていたら False。

    SETNX（nx=True）は「キーが無い時だけ書く」という操作で、
    Redis 側で1つの命令として実行される。だから2回のタップが
    同時に来ても、必ず片方だけが True を受け取る。

    TTL を付けるのは、保存中に落ちた時に鍵が残り続けないため。
    """
    return bool(
        get_redis().set(f"lock:{name}:{telegram_id}", "1", nx=True, ex=ttl)
    )


def release_lock(name: str, telegram_id: int) -> None:
    get_redis().delete(f"lock:{name}:{telegram_id}")
    



    