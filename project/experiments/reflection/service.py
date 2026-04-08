from typing import Any, Dict
from core.notion_client import get_notion_client
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from narrative_app.notion_repos.notion_repos import get_or_create_member_by_telegram
from core.config import (
    CHATBOT_TELEGRAM_BOT_TOKEN,
    NOTION_CHAT_API_KEY,
    NOTION_REFLECTION_ID,
    NOTION_REFLECTION_ITEM_ID,
    NOTION_REFLECTION_SESSION_ID,
    NOTION_REFLECTION_MESSAGE_ID,
    NOTION_REFLECTION_RESPONSE_ID,
    NOTION_MEMBER_ID,
)
from datetime import datetime, timedelta, timezone

# ＜下記はtelegramのupdateからの情報＞
# {
#   "update_id": 12345678,
#   "message": {
#     "message_id": 100,
#     "from": {
#       "id": 987654321,  // ← これが User ID
#       "is_bot": false,
#       "first_name": "Gopal",
#       "username": "gopal_tech",
#       "language_code": "ja"
#     },
#     "chat": {
#       "id": 987654321,  // 個別チャットの場合は from.id と同じ
#       "type": "private"
#     },
#     "date": 1640000000,
#     "text": "こんにちは"
#   }
# }

# Dictで会話の状態管理。（メッセージを送った時に、Notion\Chat APIを読みに行かないための）
# 状態は、CLOSE/OPENの二つだけ
user_status_memory = {}    

# /startでYes/Noを押した時の処理
async def start_button_handler(update):
    query = update.callback_query
    await query.answer()


async def confirm_start_reflection_inline_button(chat_id: int):
    bot = Bot(token=CHATBOT_TELEGRAM_BOT_TOKEN)
    keyboard = [
            [
                InlineKeyboardButton('Yes', callback_data='yes_clicked'),
                InlineKeyboardButton('No', callback_data='no_clicked'),
            ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=chat_id, text='Please choose', reply_markup=reply_markup)

async def show_help_inline_button(chat_id:int):
    keyboard = [
            [
                InlineKeyboardButton('Yes', callback_data='yes_clicked'),
                InlineKeyboardButton('No', callback_data='no_clicked'),
            ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=chat_id, text='Start the Reflection session by sending "/start". If you want to quit the current session, send "/quit"', reply_markup=reply_markup)
    

# TODO
# InlineKeyboardButton
# AgenticLoop

async def handle_user_message(update:Dict[str,Any]):
    if 'callback_query' in update:
        # ボタンが押された時の処理
        data = update['callback_query']['data']
        user_id = update['callback_query']['from']['id']
        if data == 'yes_clicked':
            print(user_status_memory[user_id])
            # NotionのReflectionSessionの開始＝新規レコードの作成。これが終わったら次。

            # ここでAgentを呼び出す。作成したNotionDBを見にいくところまで待ってもらう
            

    if 'message' in update:
        user_id = update['message']['from']['id']
     # 通常メッセージの処理...
    text = update['message'].get('text')    
    chat_id=update['message']['chat']['id']
    

    # 初回＋前回Reflection Sessionを最後まで終了時
    if (user_status_memory.get(user_id,'') in ['CLOSE','']):
        if text == '/start':
           await confirm_start_reflection_inline_button(chat_id)
           #  Reflectionを開始したら、メモリのstatusをOPENにする＆Notionに新規ページのcreated & Agentを呼ぶ
           user_status_memory[user_id] = 'OPEN'
        elif text == '/help':
            await show_help_inline_button(chat_id)
        return
    # 前回一度初めて、途中で辞めた場合（）
    if (user_status_memory.get(user_id) == 'OPEN'):
        if text == '/quit':
            user_status_memory[user_id] = 'OPEN'
            # NOTIONのOPENのページを削除する
        else:
            # Agentを呼ぶ
            return 
    return