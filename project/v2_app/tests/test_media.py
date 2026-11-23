"""media.py の命名規則のテスト。R2 には繋がない。"""

from __future__ import annotations

from datetime import datetime, timezone

from v2_app.core import media
from v2_app.core.config import R2_FOLDER
from v2_app.tests.harness import Suite

suite = Suite("media (命名のみ)")


@suite.case("拡張子はファイル名から取る")
def _() -> None:
    assert media._ext("photo.JPG", "") == ".jpg"
    assert media._ext("a/b/c.mp3", "") == ".mp3"


@suite.case("ファイル名に拡張子が無ければ content_type から推測する")
def _() -> None:
    assert media._ext("file", "image/jpeg") in (".jpg", ".jpe", ".jpeg")
    assert media._ext("", "audio/ogg") == ".ogg"


@suite.case(".oga は .ogg に寄せる（Notionが読めないため）")
def _() -> None:
    """⚠️ Telegram は音声メッセージを `.oga` で返す。Notion は
    `.oga` を知らず「Couldn't read that file」になる
    （2026-10-22に実機で発覚）。中身は同じ Ogg。
    """
    assert media._ext("voice/file_5.oga", "audio/ogg") == ".ogg"
    assert media._ext("voice/file_5.OGA", "audio/ogg") == ".ogg"
    assert media._ext("file.opus", "audio/ogg") == ".ogg"
    assert media._ext("", "audio/oga") == ".ogg"
    # 他の形式は触らない
    assert media._ext("a.mp3", "audio/mpeg") == ".mp3"
    assert media._ext("a.m4a", "audio/mp4") == ".m4a"


@suite.case("Content-Type も標準形にする")
def _() -> None:
    """⚠️ 標準でない型を R2 に載せると、音声として扱われない。"""
    assert media.normalize_type("audio/oga") == "audio/ogg"
    assert media.normalize_type("audio/opus") == "audio/ogg"
    assert media.normalize_type("audio/ogg; codecs=opus") == "audio/ogg"
    # 他はそのまま
    assert media.normalize_type("audio/mpeg") == "audio/mpeg"
    assert media.normalize_type("image/jpeg") == "image/jpeg"


@suite.case("推測もできなければ拡張子なし")
def _() -> None:
    assert media._ext("file", "application/octet-stream") == ""


@suite.case("パスに含まれるドットを拡張子と誤認しない")
def _() -> None:
    assert media._ext("https://a.example.com/path/file", "image/png") == ".png"


@suite.case("object key は フォルダ/アプリ/年月/種別_ID_乱数.拡張子")
def _() -> None:
    key = media.make_object_key("reflection", 12345, "photo", "x.jpg", "image/jpeg")
    ym = datetime.now(timezone.utc).strftime("%Y%m")
    assert key.startswith(f"{R2_FOLDER}/reflection/{ym}/photo_12345_"), key
    assert key.endswith(".jpg"), key


@suite.case("同じ入力でも key は毎回変わる（上書き事故を防ぐ）")
def _() -> None:
    args = ("reflection", 12345, "photo", "x.jpg", "image/jpeg")
    keys = {media.make_object_key(*args) for _ in range(50)}
    assert len(keys) == 50, len(keys)


@suite.case("key の末尾は Notion の表示名になるので読める形になっている")
def _() -> None:
    key = media.make_object_key("practice", 777, "audio", "", "audio/ogg")
    name = key.rsplit("/", 1)[-1]
    assert name.startswith("audio_777_")
    assert name.endswith(".ogg")


@suite.case("大きすぎるファイルは upload_bytes で弾く")
def _() -> None:
    import asyncio

    big = b"x" * (media.MAX_BYTES + 1)
    try:
        asyncio.run(media.upload_bytes(big, "k", "application/octet-stream"))
    except ValueError:
        return
    raise AssertionError("ValueError が出なかった")


@suite.case("空のファイルも弾く")
def _() -> None:
    import asyncio

    try:
        asyncio.run(media.upload_bytes(b"", "k", "application/octet-stream"))
    except ValueError:
        return
    raise AssertionError("ValueError が出なかった")
