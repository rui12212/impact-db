# service.py 変更点まとめ

## 1. importの変更（1〜4行目）

**変更前:**
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
```

**変更後:**
```python
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
```

- `Update`, `telegram.ext` 系は全て削除
- `Bot` を追加

---

## 2. configのimportに `CHATBOT_TELEGRAM_BOT_TOKEN` を追加（6〜14行目）

**変更後:**
```python
from core.config import (
    CHATBOT_TELEGRAM_BOT_TOKEN,   # ← 追加
    NOTION_CHAT_API_KEY,
    ...
)
```

---

## 3. `confirm_start_reflection_inline_button` の変更

**変更前:**
```python
async def confirm_start_reflection_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ...
    await update.message.reply_text('Please choose', reply_markup)
```

**変更後:**
```python
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
```

---

## 4. `show_help_inline_button` の変更

**変更前:**
```python
async def show_help_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ...
    await update.message.reply_text('...', reply_markup)
```

**変更後:**
```python
async def show_help_inline_button(chat_id: int):
    bot = Bot(token=CHATBOT_TELEGRAM_BOT_TOKEN)
    keyboard = [
        [
            InlineKeyboardButton('Yes', callback_data='yes_clicked'),
            InlineKeyboardButton('No', callback_data='no_clicked'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=chat_id, text='Start the Reflection session by sending "/start". If you want to quit the current session, send "/quit"', reply_markup=reply_markup)
```

---

## 5. `handle_user_message` の変更

**変更前:**
```python
def handle_user_message(update, context):
    text = update['message'].get('text')
    user_id = update['message']['from']['id']
    ...
    confirm_start_reflection_inline_button(update, context)
    ...
    show_help_inline_button()
```

**変更後:**
```python
async def handle_user_message(update: Dict[str, Any]):
    text = update['message'].get('text')
    user_id = update['message']['from']['id']
    chat_id = update['message']['chat']['id']   # ← 追加
    ...
    await confirm_start_reflection_inline_button(chat_id)
    ...
    await show_help_inline_button(chat_id)
```

変更ポイント:
- `def` → `async def`
- 引数から `context` を削除
- `chat_id` を dictから取得する行を追加
- 関数呼び出しに `await` を追加、引数を `chat_id` に変更
