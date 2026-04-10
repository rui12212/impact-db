from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from core.config import PORTFOLIO_TELEGRAM_BOT_TOKEN
# ０：end/help以外のコマンドラインは常にhelpが発生するようにする

BOT_TOKEN = PORTFOLIO_TELEGRAM_BOT_TOKEN

HELP_TEXT = """\
/help - Show this command line
/end - Finish recording and start new record n\
"""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)

async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Finised recording. New recorded started! n\ Please send Text/Voice Message/Video/Photos!")
    # Notionの既存レコードがあるか。あれば全件Close
    # Notionの新規レコードのOpen。直前のメッセージがコマンドでなければ、直近メッセージをNotionへ。


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)

async def handle_portfolio_update(update_data: dict) -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    async with app:
        update = Update.de_json(update_data, app.bot)
        await app.process_update(update)


# １A：Close/継続のPopup処理

# １A1：Closeする場合の処理を記載
# ー＞Closeで全てのOpenなレコードを取り出して、’Close’にする。日付指定してレコードを更新する機能はまだ入れない
# →直近で入力したデータで新規Notionレコード作成

# １A2：継続の場合
# →Openの中でも最新のRecord一件だけを取ってくる
# →直近の入力データを

# 1:まずは、受け取ったら前回のtelegramBotへの投稿から2時間以上経っているかの確認
# ー＞is_closedするかどうかの確認Popup

# ２：データ種類の確認
# text＊RawデータでNotionへ保存=>
# 写真：Cloudflare R2に保存
# 動画：Cloudflare R2に保存
# 音声：マイクを使った音声ファイルにも対応させる。
# →ここらの処理はすでにある