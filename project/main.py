import os, logging
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from narrative_app.service import handle_telegram_update
from core.config import IMPACT_TELEGRAM_SECRET_TOKEN, NARRATIVE_TELEGRAM_SECRET_TOKEN
from impact_app.service import impact_process_update; load_dotenv()
import requests
import ulid 

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)
impact_secret_token = IMPACT_TELEGRAM_SECRET_TOKEN
narrative_secret_token = NARRATIVE_TELEGRAM_SECRET_TOKEN

# Fast API
app = FastAPI()

@app.get('/healthz')
def healthz():
    return {'ok': True, 'time': datetime.now(timezone.utc).isoformat()}

@app.post('/telegram/impact/webhook')
async def impact_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != IMPACT_TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail='Invalid secret token')
    update = await request.json()
    # すぐACK、重い処理は裏で
    background.add_task(impact_process_update, update)
    return JSONResponse({'ok': True})

@app.post('/telegram/narrative/webhook')
async def narrative_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != NARRATIVE_TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid secret Token for narrative bot")
    update = await request.json()
    background.add_task(handle_telegram_update,update)
    return JSONResponse({"ok": True})