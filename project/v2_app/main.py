from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from v2_app.core import redis_client
from v2_app.core.config import TELEGRAM_SECRET_TOKEN, assert_configured
from v2_app.router import dispatcher

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("impactdb.v2")

app = FastAPI(title="Impact DB V2")


@app.on_event("startup")
async def startup() -> None:
    """設定漏れは起動時に落とす。

    足りないまま起動すると、先生が最初のメッセージを送った時に
    初めて Notion が unauthorized を返す。原因が分かりにくい。
    """
    assert_configured()
    if not redis_client.ping():
        raise RuntimeError("Redisに繋がらないです")
    log.info("V2 起動完了")


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "ok": True,
        "redis": redis_client.ping(),
        "time": datetime.now(timezone.utc).isoformat(),
    }


async def _handle(update: Dict[str, Any]) -> None:
    """裏で動かす本体。ここで必ず例外を止める。

    BackgroundTasks の中で例外が出ると、ログに出るだけで
    誰にも伝わらない。先生は無言のまま待たされる。
    """
    try:
        await dispatcher.handle_update(update)
    except Exception:
        log.exception("update の処理に失敗 update_id=%s", update.get("update_id"))


@app.post("/telegram/v2/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> JSONResponse:
    """Telegram からの受け口。

    ⚠️ 重い処理を待ってから200を返すと、Telegram が
    「返事が無い」と判断して同じ update を再送してくる。
    だから先に200を返して、処理は裏に回す。
    """
    if x_telegram_bot_api_secret_token != TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    background.add_task(_handle, update)
    return JSONResponse({"ok": True})
