"""
Gemini API の月次リクエスト制限モジュール

JSONファイルでリクエスト数を追跡し、月間上限を超えた場合にブロックする。
カウンターは月が変わると自動的にリセットされる。
"""

import json
import os
import logging
import threading
from datetime import datetime

log = logging.getLogger("impactdb")

_QUOTA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    ".gemini_usage.json",
)

_MONTHLY_LIMIT = int(os.getenv("GEMINI_MONTHLY_LIMIT", "100"))

_lock = threading.Lock()


class GeminiQuotaExceeded(Exception):
    """月次リクエスト上限を超過した場合の例外"""
    pass


def _read_usage() -> dict:
    if not os.path.exists(_QUOTA_FILE):
        return {}
    try:
        with open(_QUOTA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_usage(data: dict) -> None:
    # "w" モードはファイルが無ければ 新規作成あれば上書き
    with open(_QUOTA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def get_monthly_count() -> int:
    """今月のリクエスト数を返す"""
    data = _read_usage()
    return data.get(_current_month_key(), 0)


def check_and_increment() -> int:
    """
    月次上限をチェックし、まだ余裕があればカウンターを+1して現在の値を返す。
    上限超過時は GeminiQuotaExceeded を送出する。
    """
    with _lock:
        key = _current_month_key()
        data = _read_usage()
        # 月キーが変わることで自動リセット。keyには月が入る。keyがない場合は、defaultでdataは0になる
        current = data.get(key, 0)

        if current >= _MONTHLY_LIMIT:
            raise GeminiQuotaExceeded(
                f"Gemini API monthly limit reached: {current}/{_MONTHLY_LIMIT} "
                f"(month: {key})"
            )

        data[key] = current + 1
        _write_usage(data)
        log.info(f"Gemini API usage: {current + 1}/{_MONTHLY_LIMIT} (month: {key})")
        return current + 1
