"""
Inline Keyboard テスト用Bot
- メッセージにくっつくボタン
- 押してもチャットにテキストが残らない
- ボタンを押した後にメッセージを書き換え

使い方:
1. @BotFather で新しいBotを作成し、トークンを取得
2. BOT_TOKEN=xxx python test_inline_keyboard.py
"""

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

BOT_TOKEN = "8623142793:AAH17X0H1qSrgwG-DhwvaCeGGiZFBR71Oh8"

MODE_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📝 振り返り", callback_data="mode_reflection"),
        InlineKeyboardButton("📋 授業研究", callback_data="mode_lesson"),
        InlineKeyboardButton("📖 授業案", callback_data="mode_plan"),
    ],
    [
        InlineKeyboardButton("⚙️ 情報を変更", callback_data="mode_settings"),
    ],
])

SAVE_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ 保存する", callback_data="save"),
        InlineKeyboardButton("✏️ もう少し追加する", callback_data="add_more"),
    ]
])

BACK_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("← モードを変える", callback_data="back_to_mode")]
])

MODE_LABELS = {
    "mode_reflection": "📝 振り返り",
    "mode_lesson": "📋 授業研究",
    "mode_plan": "📖 授業案",
}

QUESTIONS = [
    "それは何の教科の授業でしたか？🏫",
    "どんな学びがありましたか？教えてください 📖",
    "写真や動画はありますか？あれば送ってください。なければ「なし」と教えてください 📸",
    "TEACHER_SELECT",
]

TEACHER_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Ako", callback_data="teacher_Ako"),
        InlineKeyboardButton("Ren", callback_data="teacher_Ren"),
    ],
    [
        InlineKeyboardButton("Seyha", callback_data="teacher_Seyha"),
        InlineKeyboardButton("Chomran", callback_data="teacher_Chomran"),
    ],
    [
        InlineKeyboardButton("自分", callback_data="teacher_自分"),
    ],
])


def get_step(context):
    return context.user_data.get("step", 0)


def get_answers(context):
    return context.user_data.get("answers", [])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "こんにちは！何を記録しますか？👇",
        reply_markup=MODE_KEYBOARD,
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_mode":
        context.user_data.clear()
        await query.edit_message_text(
            "何を記録しますか？👇",
            reply_markup=MODE_KEYBOARD,
        )

    elif query.data in MODE_LABELS:
        context.user_data["mode"] = query.data
        context.user_data["step"] = 0
        context.user_data["answers"] = []
        label = MODE_LABELS[query.data]
        await query.message.reply_text(
            f"✅ {label} モードに入りました。\n\n"
            f"テキストや音声で教えてください。\n"
            f"まず最初に — {QUESTIONS[0]}",
            reply_markup=BACK_KEYBOARD,
        )

    elif query.data == "mode_settings":
        await query.message.reply_text(
            "⚙️ 設定モード\n\n"
            "現在の登録情報:\n"
            "  名前: ソピア\n"
            "  学校: プノンペン小学校\n\n"
            "変更したい内容を教えてください。",
            reply_markup=BACK_KEYBOARD,
        )

    elif query.data == "save":
        answers = get_answers(context)
        mode = context.user_data.get("mode", "mode_reflection")
        label = MODE_LABELS.get(mode, "振り返り")

        subject = answers[0] if len(answers) > 0 else "—"
        learning = answers[1] if len(answers) > 1 else "—"
        media = answers[2] if len(answers) > 2 else "—"
        teacher = answers[3] if len(answers) > 3 else "—"

        await query.edit_message_text(
            f"🎉 保存しました！\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 種類: {label}\n"
            f"🏫 教科: {subject}\n"
            f"📖 学び: {learning}\n"
            f"📸 メディア: {media}\n"
            f"👩‍🏫 先生: {teacher}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Notionに追加されました！\n"
            f"マイページに反映されます。"
        )
        context.user_data.clear()

        await query.message.reply_text(
            "続けて記録しますか？👇",
            reply_markup=MODE_KEYBOARD,
        )

    elif query.data.startswith("teacher_"):
        teacher = query.data.replace("teacher_", "")
        answers = get_answers(context)
        answers.append(teacher)
        context.user_data["answers"] = answers
        step = get_step(context)
        context.user_data["step"] = step + 1

        subject = answers[0] if len(answers) > 0 else "—"
        learning = answers[1] if len(answers) > 1 else "—"
        media = answers[2] if len(answers) > 2 else "—"

        await query.edit_message_text(
            f"授業者は誰ですか？👇\n\n→ {teacher}"
        )

        await query.message.reply_text(
            f"📋 整理しました！\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏫 教科: {subject}\n"
            f"📖 学び: {learning}\n"
            f"📸 メディア: {media}\n"
            f"👩‍🏫 授業者: {teacher}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"この内容で保存しますか？",
            reply_markup=SAVE_KEYBOARD,
        )

    elif query.data == "add_more":
        context.user_data["step"] = 0
        context.user_data["answers"] = []
        await query.edit_message_text(
            "もう少し教えてください！\n\n"
            f"{QUESTIONS[0]}"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if not mode:
        await update.message.reply_text(
            "何を記録しますか？👇",
            reply_markup=MODE_KEYBOARD,
        )
        return

    step = get_step(context)
    answers = get_answers(context)

    print(f"[DEBUG] step={step}, text={update.message.text}")

    answers.append(update.message.text)
    context.user_data["answers"] = answers
    context.user_data["step"] = step + 1

    print(f"[DEBUG] answers={answers}, next_step={step + 1}, total_q={len(QUESTIONS)}")

    if step + 1 < len(QUESTIONS):
        next_question = QUESTIONS[step + 1]
        if next_question == "TEACHER_SELECT":
            print(f"[DEBUG] showing teacher selection")
            await update.message.reply_text(
                "ありがとうございます！\n\n授業者は誰ですか？👇",
                reply_markup=TEACHER_KEYBOARD,
            )
        else:
            print(f"[DEBUG] sending question: {next_question}")
            await update.message.reply_text(
                f"ありがとうございます！\n\n{next_question}"
            )
    else:
        subject = answers[0] if len(answers) > 0 else "—"
        learning = answers[1] if len(answers) > 1 else "—"
        media = answers[2] if len(answers) > 2 else "—"

        await update.message.reply_text(
            f"📋 整理しました！\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏫 教科: {subject}\n"
            f"📖 学び: {learning}\n"
            f"📸 メディア: {media}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"この内容で保存しますか？",
            reply_markup=SAVE_KEYBOARD,
        )


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if not mode:
        await update.message.reply_text(
            "まずモードを選んでください👇",
            reply_markup=MODE_KEYBOARD,
        )
        return

    step = get_step(context)
    answers = get_answers(context)

    if update.message.voice or update.message.audio:
        answers.append("🎤 音声メッセージ（文字起こし済み）")
    elif update.message.photo:
        answers.append("📷 写真あり")
    elif update.message.video:
        answers.append("🎥 動画あり")
    else:
        answers.append("📎 ファイルあり")

    context.user_data["answers"] = answers
    context.user_data["step"] = step + 1

    if step + 1 < len(QUESTIONS):
        next_question = QUESTIONS[step + 1]
        await update.message.reply_text(
            f"ありがとうございます！受け取りました。\n\n{next_question}"
        )
    else:
        subject = answers[0] if len(answers) > 0 else "—"
        learning = answers[1] if len(answers) > 1 else "—"
        media = answers[2] if len(answers) > 2 else "—"

        await update.message.reply_text(
            f"📋 整理しました！\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏫 教科: {subject}\n"
            f"📖 学び: {learning}\n"
            f"📸 メディア: {media}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"この内容で保存しますか？",
            reply_markup=SAVE_KEYBOARD,
        )


def main():
    if not BOT_TOKEN:
        print("エラー: BOT_TOKEN を環境変数に設定してください")
        print("  BOT_TOKEN=xxx python test_ai_conversation_demo.py")
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        handle_media,
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("AI模擬対話デモBot起動中...")
    print("Ctrl+C で停止")
    app.run_polling()


if __name__ == "__main__":
    main()
