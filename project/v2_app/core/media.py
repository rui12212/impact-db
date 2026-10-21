from __future__ import annotations

import asyncio
import io
import mimetypes
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
import httpx
from botocore.client import Config

from v2_app.core.config import (
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET_NAME,
    R2_FOLDER,
    R2_PUBLIC_URL_BASE,
    R2_SECRET_ACCESS_KEY,
)

DOWNLOAD_TIMEOUT = 180
# Telegram Bot API が配信できる上限と同じ
MAX_BYTES = 50 * 1024 * 1024

# Telegram が実際に送ってくる型。標準の mimetypes は audio/ogg を知らず
# None を返すため、よく通る経路は明示的に持つ
EXT_BY_TYPE = {
    "audio/ogg": ".ogg",        # 音声メッセージ（voice）
    "audio/oga": ".oga",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-wav": ".wav",
    "image/jpeg": ".jpg",       # 写真（photo）
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",        # 動画・ビデオメッセージ
    "video/quicktime": ".mov",
    "application/pdf": ".pdf",
}

# ⚠️ **Notion は拡張子で再生できるか判断する**（2026-10-22に実機で発覚）。
#
# Telegram は音声メッセージのファイルパスを `.oga` で返してくるが、
# Notion は `.oga` を知らず「Couldn't read that file」になる。
# 中身は同じ Ogg なので、**標準形に寄せる**だけで読めるようになる。
#
# Content-Type も合わせて直す。`audio/oga` は標準ではない
NORMALIZE_EXT = {
    ".oga": ".ogg",
    ".opus": ".ogg",   # Telegram の voice は Opus/Ogg
}
NORMALIZE_TYPE = {
    "audio/oga": "audio/ogg",
    "audio/opus": "audio/ogg",
}


def normalize_type(content_type: str) -> str:
    """R2 に載せる Content-Type。標準ではない型を直す。

    ⚠️ **パラメータ（`; codecs=opus` など）は落とす。** メディアの
    扱いに影響しないうえ、残すと「直した型」と「素通りの型」で
    形が揃わない。
    """
    ctype = (content_type or "").split(";")[0].strip().lower()
    if not ctype:
        return content_type
    return NORMALIZE_TYPE.get(ctype, ctype)


_s3 = None

def get_s3():
    global _s3
    if _s3 is None:
        if not R2_ACCOUNT_ID:
            raise RuntimeError("R2_ACCOUNT_IDが設定されていないです")
        _s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
    return _s3

def _ext(file_name: str, content_type: str) -> str:
    tail = file_name.rsplit("/", 1)[-1]
    if "." in tail:
        ext = "." + tail.rsplit(".", 1)[-1].lower()
        # ⚠️ Notion が知らない拡張子を標準形に寄せる（NORMALIZE_EXT）
        return NORMALIZE_EXT.get(ext, ext)

    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype in EXT_BY_TYPE:
        return NORMALIZE_EXT.get(EXT_BY_TYPE[ctype], EXT_BY_TYPE[ctype])
    if ctype in ("", "application/octet-stream"):
        return ""
    ext = mimetypes.guess_extension(ctype) or ""
    return NORMALIZE_EXT.get(ext, ext)


def make_object_key(
    app: str, telegram_id: int, kind: str, file_name: str, content_type: str
) -> str:
    """R2上のパス。

    アプリ別・月別に分け、末尾に乱数を足して衝突をなくす。
    ファイル名はNotionの files プロパティにそのまま表示名として出る
    （flow._to_prop が URL の末尾から名前を取る）ので読める形にしておく。
    """
    ym = datetime.now(timezone.utc).strftime("%Y%m")
    stem = f"{kind}_{telegram_id}_{uuid.uuid4().hex[:8]}"
    return f"{R2_FOLDER}/{app}/{ym}/{stem}{_ext(file_name, content_type)}"

def _put(key: str, data: bytes, content_type: str) -> None:
    get_s3().upload_fileobj(
        io.BytesIO(data),
        R2_BUCKET_NAME,
        key,
        # ⚠️ 標準ではない型をそのまま載せると、Notion やブラウザが
        # 音声として扱ってくれない（NORMALIZE_TYPE）
        ExtraArgs={"ContentType": normalize_type(content_type)},
    )

async def upload_bytes(data: bytes, key: str, content_type: str) -> str:
    """boto3は同期なので別スレッドに逃がす。イベントループを止めないため。"""
    if not data:
        raise ValueError("中身が空です")
    if len(data) > MAX_BYTES:
        raise ValueError(f"ファイルが大きすぎます: {len(data)} bytes")
    await asyncio.to_thread(_put, key, data, content_type)
    return f"{R2_PUBLIC_URL_BASE}/{key}"


async def upload_from_url(
    url: str,
    *,
    app: str,
    telegram_id: int,
    kind: str = "file",
    file_name: str = "",
    content_type: str = "application/octet-stream",
) -> str:
    """TelegramのファイルURLから落として、R2に置いて公開URLを返す。"""
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
        res = await client.get(url)
        res.raise_for_status()
        data = res.content

    key = make_object_key(app, telegram_id, kind, file_name or url, content_type)
    return await upload_bytes(data, key, content_type)


async def upload_from_path(
    path: str,
    *,
    app: str,
    telegram_id: int,
    kind: str = "file",
    content_type: Optional[str] = None,
) -> str:
    """ローカルファイルをR2に置く。バッチ（グラフ画像など）用。"""
    ctype = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
    data = await asyncio.to_thread(lambda: open(path, "rb").read())
    key = make_object_key(app, telegram_id, kind, path, ctype)
    return await upload_bytes(data, key, ctype)