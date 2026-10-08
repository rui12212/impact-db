"""
Reply Keyboard テスト用Bot
- is_persistent: true で常時表示
- resize_keyboard: true でコンパクト表示
- one_time_keyboard のテストも可能

使い方:
1. @BotFather で新しいBotを作成し、トークンを取得
2. BOT_TOKEN=xxx python test_reply_keyboard.py
"""

import os
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

BOT_TOKEN = "8788660026:AAELD_WXoeXwJvTFkaBmGCKbkstD6Nz7l34"

MODES = {
    "📝 振り返り": "reflection",
    "📋 授業研究": "lesson",
    "📖 授業案": "plan",
}

KEYBOARD = ReplyKeyboardMarkup(
    [["📝 振り返り", "📋 授業研究", "📖 授業案"]],
    resize_keyboard=True,
    is_persistent=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    param = context.args[0] if context.args else None
    if param and param in ("reflection", "lesson", "plan"):
        context.user_data["mode"] = param
        label = {"reflection": "📝 振り返り", "lesson": "📋 授業研究", "plan": "📖 授業案"}[param]
        await update.message.reply_text(
            f"Deep Linkで {label} モードに入りました。\n入力してください。",
            reply_markup=KEYBOARD,
        )
    else:
        await update.message.reply_text(
            "Reply Keyboard テストBotです。\n"
            "下のボタンからモードを選んでください。",
            reply_markup=KEYBOARD,
        )


async def handle_mode_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text in MODES:
        mode = MODES[text]
        context.user_data["mode"] = mode
        await update.message.reply_text(
            f"✅ {text} モードに入りました。\n"
            f"テキストや音声を送ってください。\n\n"
            f"（モードを変えたい場合は下のボタンを押してください）",
            reply_markup=KEYBOARD,
        )
    else:
        mode = context.user_data.get("mode")
        if mode:
            label = [k for k, v in MODES.items() if v == mode][0]
            await update.message.reply_text(
                f"[{label}モード] 受け取りました:\n「{text}」\n\n"
                f"（実際のBotではここでAIが応答します）",
                reply_markup=KEYBOARD,
            )
        else:
            await update.message.reply_text(
                "まずモードを選んでください👇",
                reply_markup=KEYBOARD,
            )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if mode:
        label = [k for k, v in MODES.items() if v == mode][0]
        await update.message.reply_text(
            f"[{label}モード] 音声メッセージを受け取りました。\n"
            f"（実際のBotではここでWhisperで文字起こしします）",
            reply_markup=KEYBOARD,
        )
    else:
        await update.message.reply_text(
            "まずモードを選んでください👇",
            reply_markup=KEYBOARD,
        )


def main():
    if not BOT_TOKEN:
        print("エラー: BOT_TOKEN を環境変数に設定してください")
        print("  BOT_TOKEN=xxx python test_reply_keyboard.py")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mode_select))

    print("Reply Keyboard テストBot起動中...")
    print(f"Deep Link テスト: https://t.me/<bot_username>?start=reflection")
    app.run_polling()


if __name__ == "__main__":
    main()
