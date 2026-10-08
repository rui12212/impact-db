from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from v2_app.core.config import (
    SLACK_BOT_TOKEN,
    SLACK_CHANNEL_MAP,
    SLACK_DEFAULT_CHANNEL,
)

log = logging.getLogger("impactdb.v2")

API = "https://slack.com/api"
TIMEOUT = 15


def channel_for(school_name: str = "") -> str:
    """学校名 → 投稿先チャンネル。マップに無ければ既定のチャンネル。"""
    if school_name and school_name in SLACK_CHANNEL_MAP:
        return SLACK_CHANNEL_MAP[school_name]
    return SLACK_DEFAULT_CHANNEL


async def post(
    text: str, *, channel: str = "", school_name: str = ""
) -> bool:
    """Slackに投稿する。成功したら True。

    失敗しても例外にしない。Slackは通知であって記録の正本ではない
    （正本はNotion）。投稿が落ちた時点で保存はもう終わっている。

    未設定（トークンや投稿先が空）なら何もせず False を返す。
    Slackを使わない構成でもBotが動くようにするため。
    """
    if not SLACK_BOT_TOKEN:
        log.info("Slack未設定のため投稿しない")
        return False

    target = channel or channel_for(school_name)
    if not target:
        log.warning("Slackの投稿先が決まっていない")
        return False

    if not text:
        return False

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.post(
                f"{API}/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                json={"channel": target, "text": text},
            )
        data = res.json()
    except Exception as e:
        log.warning("Slack post failed: %s", e)
        return False

    if not data.get("ok"):
        # not_in_channel / channel_not_found / missing_scope がよく出る
        log.warning(
            "Slack post failed: %s (channel=%s)", data.get("error"), target
        )
        return False

    return True


async def auth_test() -> Dict[str, Any]:
    """トークンが生きているかの確認。投稿はしない。

    スクリプトから呼んで疎通を見る用。ここだけ例外を上げる
    （確認したいのに静かに False が返ると原因が分からない）。
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.post(
            f"{API}/auth.test",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        )
    data = res.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack auth.test failed: {data}")
    return data
