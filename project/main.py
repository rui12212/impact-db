import os, logging, asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from narrative_app.service import handle_telegram_update
from core.config import (
    IMPACT_TELEGRAM_SECRET_TOKEN,
    NARRATIVE_TELEGRAM_SECRET_TOKEN,
    NARRATIVE_TELEGRAM_BOT_TOKEN,
    IMPACT_TELEGRAM_BOT_TOKEN
)
from impact_app.service import impact_process_update; load_dotenv()
import requests
import ulid

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb')

impact_secret_token = IMPACT_TELEGRAM_SECRET_TOKEN
narrative_secret_token = NARRATIVE_TELEGRAM_SECRET_TOKEN

# Fast API
app = FastAPI()

# Polling mode flag
USE_POLLING = os.getenv("USE_POLLING")

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

# Polling mode for local development
if USE_POLLING:
    # Store bot applications globally for shutdown
    narrative_app_global = None
    impact_app_global = None

    @app.on_event("startup")
    async def start_polling():
        global narrative_app_global, impact_app_global
        log.info("Starting Telegram bots in POLLING mode for local development")

        try:
            from telegram import Update
            from telegram.ext import Application, MessageHandler, filters, ContextTypes

            # Narrative Bot
            narrative_app_global = Application.builder().token(NARRATIVE_TELEGRAM_BOT_TOKEN).build()

            async def narrative_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
                try:
                    handle_telegram_update(update.to_dict())
                except Exception as e:
                    log.exception(f"Error in narrative handler: {e}")

            narrative_app_global.add_handler(MessageHandler(filters.ALL, narrative_handler))

            # Impact Bot
            impact_app_global = Application.builder().token(IMPACT_TELEGRAM_BOT_TOKEN).build()

            async def impact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
                try:
                    impact_process_update(update.to_dict())
                except Exception as e:
                    log.exception(f"Error in impact handler: {e}")

            impact_app_global.add_handler(MessageHandler(filters.ALL, impact_handler))

            # Initialize and start polling
            await narrative_app_global.initialize()
            await impact_app_global.initialize()

            # Delete webhooks
            await narrative_app_global.bot.delete_webhook(drop_pending_updates=True)
            await impact_app_global.bot.delete_webhook(drop_pending_updates=True)

            log.info("Webhooks deleted, starting polling...")

            # Start both bots
            await narrative_app_global.start()
            await impact_app_global.start()

            # Start polling in background
            asyncio.create_task(narrative_app_global.updater.start_polling(drop_pending_updates=True))
            asyncio.create_task(impact_app_global.updater.start_polling(drop_pending_updates=True))

            log.info("✅ Both bots are now running in polling mode")

        except Exception as e:
            log.exception(f"Failed to start polling mode: {e}")

    @app.on_event("shutdown")
    async def stop_polling():
        global narrative_app_global, impact_app_global
        log.info("Stopping polling mode...")

        try:
            if narrative_app_global:
                await narrative_app_global.updater.stop()
                await narrative_app_global.stop()
                await narrative_app_global.shutdown()

            if impact_app_global:
                await impact_app_global.updater.stop()
                await impact_app_global.stop()
                await impact_app_global.shutdown()

            log.info("✅ Polling mode stopped cleanly")
        except Exception as e:
            log.exception(f"Error stopping polling mode: {e}")