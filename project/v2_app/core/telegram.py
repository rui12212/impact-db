from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from v2_app.core.config import TELEGRAM_BOT_TOKEN

log = logging.getLogger("impactdb.v2")

API_BASE = "https://api.telegram.org"
TIMEOUT = 30
MAX_ATTEMPTS = 3

# Telegram の1メッセージの上限
MAX_TEXT = 4096


class TelegramError(RuntimeError):
    pass


def _url(method: str) -> str:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("V2_TELEGRAM_BOT_TOKENが設定されていないです")
    return f"{API_BASE}/bot{TELEGRAM_BOT_TOKEN}/{method}"


async def api(method: str, **params: Any) -> Dict[str, Any]:
    """Telegram API を叩く。429 の retry_after を守る。

    reply_markup / 辞書やリストの値は JSON 文字列にして渡す必要がある。
    V1 はここで渡し忘れていてキーボードが出ていなかった。
    """
    payload = {
        k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
        for k, v in params.items()
        if v is not None
    }

    last: Optional[Exception] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                res = await client.post(_url(method), data=payload)
            data = res.json()
        except Exception as e:
            last = e
            await asyncio.sleep(min(2 ** attempt, 8))
            continue

        if data.get("ok"):
            return data["result"]

        # 429 は待つ秒数を Telegram が教えてくれる
        retry_after = (data.get("parameters") or {}).get("retry_after")
        if retry_after and attempt < MAX_ATTEMPTS:
            await asyncio.sleep(float(retry_after))
            continue

        if res.status_code >= 500 and attempt < MAX_ATTEMPTS:
            await asyncio.sleep(min(2 ** attempt, 8))
            continue

        raise TelegramError(f"{method} failed: {data}")

    raise TelegramError(f"{method} failed after {MAX_ATTEMPTS} attempts: {last}")


# --- 送信 -------------------------------------------------------------

def _split(text: str) -> List[str]:
    """4096文字で切る。改行の位置で切れれば、そこで切る。"""
    if len(text) <= MAX_TEXT:
        return [text]
    parts: List[str] = []
    rest = text
    while len(rest) > MAX_TEXT:
        cut = rest.rfind("\n", 0, MAX_TEXT)
        if cut <= 0:
            cut = MAX_TEXT
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest:
        parts.append(rest)
    return parts


async def send_message(
    chat_id: int,
    text: str,
    *,
    reply_markup: Optional[dict] = None,
    parse_mode: Optional[str] = None,
) -> Optional[int]:
    """メッセージを送る。最後に送ったものの message_id を返す。

    失敗しても例外にしない。先生への返信が1通失敗しても、
    保存済みのデータを巻き戻すわけにはいかないため。
    """
    chunks = _split(text)
    message_id: Optional[int] = None
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        try:
            result = await api(
                "sendMessage",
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
                # キーボードは最後のメッセージにだけ付ける
                reply_markup=reply_markup if is_last else None,
            )
            message_id = result.get("message_id")
        except Exception as e:
            log.warning("sendMessage failed: %s", e)
    return message_id


async def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    *,
    reply_markup: Optional[dict] = None,
) -> None:
    """送ったメッセージを書き換える。

    保存後に確認カードのボタンを消すのに使う。残しておくと
    先生がもう一度押せてしまう（連打の入口を1つ減らす）。
    """
    try:
        await api(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text[:MAX_TEXT],
            reply_markup=reply_markup,
        )
    except Exception as e:
        log.warning("editMessageText failed: %s", e)


async def delete_message(chat_id: int, message_id: int) -> None:
    """送ったメッセージを消す。

    「Thinking...」を消して本物の返信を送るのに使う。

    ⚠️ 書き換え（editMessageText）ではなく削除にしている理由:
    編集では**通知が飛ばない。** 音声の文字起こしに50秒かかる間に
    先生がアプリを離れていると、編集では返信に気づけない。
    消して送り直せば通知が鳴る。
    """
    try:
        await api("deleteMessage", chat_id=chat_id, message_id=message_id)
    except Exception as e:
        # 既に消えている・古すぎる（48時間）場合は失敗する。害はない
        log.debug("deleteMessage failed: %s", e)


async def answer_callback_query(
    callback_query_id: str, text: str = "", *, show_alert: bool = False
) -> None:
    """ボタンが押されたことへの返事。

    ⚠️ これを返さないと、押したボタンがくるくる回り続けて
    先生の画面が固まったように見える。必ず呼ぶ。
    """
    try:
        await api(
            "answerCallbackQuery",
            callback_query_id=callback_query_id,
            text=text or None,
            show_alert=show_alert or None,
        )
    except Exception as e:
        log.warning("answerCallbackQuery failed: %s", e)


async def send_chat_action(chat_id: int, action: str = "typing") -> None:
    """「入力中…」を出す。

    ⚠️ Telegramの仕様で**5秒で消える。** 1回送っただけでは
    長い処理（音声の文字起こしは50秒かかる）の間ずっと無反応に見える。
    続けたいときは typing() を使う。
    """
    try:
        await api("sendChatAction", chat_id=chat_id, action=action)
    except Exception as e:
        log.debug("sendChatAction failed: %s", e)


# sendChatAction は5秒で切れるので、それより短い間隔で送り直す
TYPING_INTERVAL = 4.0


@contextlib.asynccontextmanager
async def typing(chat_id: int, action: str = "typing"):
    """処理が終わるまで「入力中…」を出し続ける。

        async with telegram.typing(chat_id):
            ...時間のかかる処理...

    音声の文字起こしは50秒かかる。1回 sendChatAction を送るだけでは
    最初の5秒しか表示されず、残り45秒は先生から見て無反応になる。
    """
    async def loop() -> None:
        try:
            while True:
                await send_chat_action(chat_id, action)
                await asyncio.sleep(TYPING_INTERVAL)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        # 後片付けを待つ。待たないと「保留中のタスク」の警告が出る
        with contextlib.suppress(asyncio.CancelledError):
            await task


# --- ファイル ---------------------------------------------------------

async def get_file_url(file_id: str) -> str:
    """file_id → ダウンロードできるURL。

    このURLにはトークンが入っているので、外に出さない。
    media.upload_from_url() に渡して R2 に移す。
    """
    result = await api("getFile", file_id=file_id)
    file_path = result["file_path"]
    return f"{API_BASE}/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"


# --- キーボード -------------------------------------------------------

def inline_keyboard(rows: List[List[tuple]]) -> dict:
    """[[(表示文字, callback_data), ...], ...] → reply_markup。

    callback_data は 64バイトまで。長いと Telegram が黙って弾く。
    """
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in rows
        ]
    }


# --- webhook 登録（スクリプトから呼ぶ）--------------------------------

async def set_webhook(url: str, secret_token: str) -> dict:
    return await api(
        "setWebhook",
        url=url,
        secret_token=secret_token,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


async def delete_webhook() -> dict:
    return await api("deleteWebhook", drop_pending_updates=True)


async def get_webhook_info() -> dict:
    return await api("getWebhookInfo")
