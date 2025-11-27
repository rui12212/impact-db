# from fastapi import APIRouter, Body
# from narrative_app.service import handle_telegram_update

# router = APIRouter(
#     prefix="/telegram",
#     tags=["telegram"],
# )

# @router.post("/webhook")
# async def telegram_webhook(update:dict = Body(...)):
#     # Endpoint to receive./accept webhook from telegram
#     # Set webhook of Telegram to https://<your-domain>/telegram/webhook
#     # update(JSON) from telegram will be sent to handle_telegram_webhook, and no logic here

#     # if it is too heavy, call it as a backgorund-task
#     handle_telegram_update(update)
#     # return 200 to telegram quickly
#     return {"ok": True}