from __future__ import annotations

import redis

from v2_app.core.config import REDIS_URL

_client: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30
        )
    return _client

def ping() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False

