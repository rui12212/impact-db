from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from v2_app.core.config import SLACK_BOT_TOKEN, SLACK_CHANNEL_MAP

log = logging.getLogger("impactdb.v2")

API = "https://slack.com/api"
TIMEOUT = 15


def _norm(page_id: str) -> str:
    """ページIDをハイフン無しの小文字に揃える。

    ⚠️ **env に貼るIDは Notion のURLから取るのでハイフンが無い**が、
    user["school_id"] は API の relation なのでハイフン付き。
    揃えないと一致せず、**気づかないまま投稿されなくなる**
    """
    return (page_id or "").replace("-", "").lower()


# 起動時に1回だけ正規化する。投稿ごとにやる必要がない
_CHANNEL_MAP = {_norm(k): v for k, v in SLACK_CHANNEL_MAP.items()}


def channel_for(school_id: str = "") -> str:
    """School のページID → 投稿先のチャンネルID。登録が無ければ空文字。

    ⚠️ **学校名ではなくIDで引く。** 名前は Notion で変えられるが、
    user:{telegram_id} のキャッシュに TTL が無く古い名前が残る。

    ⚠️ **既定の投稿先は持たない（2026-10-25決定）。** Slackに流さない
    学校があるので、**登録が無いことを「送らない」の意思表示として扱う。**
    既定へ逃がすと、流さないと決めた学校の記録が流れ続ける
    """
    return _CHANNEL_MAP.get(_norm(school_id), "")


async def post(
    text: str, *, channel: str = "", school_id: str = ""
) -> Optional[Dict[str, str]]:
    """Slackに投稿する。成功したら {"channel": ..., "ts": ...}、失敗したら None。

    失敗しても例外にしない。Slackは通知であって記録の正本ではない
    （正本はNotion）。投稿が落ちた時点で保存はもう終わっている。

    未設定（トークンや投稿先が空）なら何もせず None を返す。
    Slackを使わない構成でもBotが動くようにするため。

    ⚠️ 返り値に channel と ts を含める。**画像を同じスレッドに
    付けるために必要。** files.completeUploadExternal は
    チャンネル名（#name）を受け取らずIDしか受け取らないが、
    chat.postMessage の応答にIDが入っているので、ここから取る
    （conversations.list を叩けば channels:read が増える）
    """
    if not SLACK_BOT_TOKEN:
        log.info("Slack未設定のため投稿しない")
        return None

    target = channel or channel_for(school_id)
    if not target:
        # ⚠️ warning にしない。**未登録は正常な状態**（流さない学校がある）
        log.info("Slackに流さない学校なので投稿しない school_id=%s", school_id)
        return None

    if not text:
        return None

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
        return None

    if not data.get("ok"):
        # not_in_channel / channel_not_found / missing_scope がよく出る
        log.warning(
            "Slack post failed: %s (channel=%s)", data.get("error"), target
        )
        return None

    return {"channel": data.get("channel", ""), "ts": data.get("ts", "")}


# ------------------------------------------------------------ ファイル添付

async def fetch(url: str) -> bytes:
    """R2の公開URLから中身を取る。

    メディアはR2に上がっていて、session には公開URLしか残っていない
    （ローカルの一時ファイルは消している）。Slackへ上げ直すには
    一度ダウンロードする必要がある。
    """
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        res = await client.get(url)
    res.raise_for_status()
    return res.content


async def upload(
    channel_id: str,
    items: List[Tuple[str, bytes]],
    *,
    thread_ts: str = "",
    comment: str = "",
) -> int:
    """ファイルを投稿する。上げられた数を返す。

    ⚠️ **古い files.upload は2025年11月に廃止された。** 3段の手順になる:

      ① files.getUploadURLExternal   置き場所のURLとファイルIDをもらう
      ② そのURLに中身をPOST          Slack APIではなくS3への直接POST
      ③ files.completeUploadExternal 共有先を決めて確定

    ③を呼ばないとファイルは破棄される。③は1回しか呼べない。

    必要なスコープは files:write。chat:write とは別なので、
    足したら**アプリを再インストールする**必要がある。
    """
    if not SLACK_BOT_TOKEN or not channel_id or not items:
        return 0

    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    uploaded: List[Dict[str, str]] = []

    async with httpx.AsyncClient(timeout=120) as client:
        for name, data in items:
            if not data:
                continue
            try:
                # ① 置き場所をもらう
                res = await client.post(
                    f"{API}/files.getUploadURLExternal",
                    headers=headers,
                    data={"filename": name, "length": str(len(data))},
                )
                got = res.json()
                if not got.get("ok"):
                    log.warning("Slack upload url failed: %s", got.get("error"))
                    continue

                # ② 中身を置く（Slack APIではない宛先）
                put = await client.post(got["upload_url"], content=data)
                put.raise_for_status()

                uploaded.append({"id": got["file_id"], "title": name})
            except Exception as e:
                log.warning("Slack upload failed (%s): %s", name, e)

        if not uploaded:
            return 0

        # ③ 確定。ここを呼ばないと破棄される
        try:
            form = {
                "files": json.dumps(uploaded),
                "channel_id": channel_id,
            }
            if thread_ts:
                form["thread_ts"] = thread_ts
            if comment:
                form["initial_comment"] = comment

            res = await client.post(
                f"{API}/files.completeUploadExternal",
                headers=headers,
                data=form,
            )
            done = res.json()
        except Exception as e:
            log.warning("Slack complete upload failed: %s", e)
            return 0

    if not done.get("ok"):
        log.warning(
            "Slack complete upload failed: %s (channel=%s)",
            done.get("error"), channel_id,
        )
        return 0

    return len(uploaded)


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
