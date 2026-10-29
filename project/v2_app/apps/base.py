from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from v2_app.core import (
    ask,
    extract,
    flow,
    media,
    notion_writer,
    session,
    slack,
    stt,
    summarize,
    telegram,
)
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

SAVE = "save"
MORE = "more"

# 写真・動画があるかを聞くボタン（2026-10-21追加）。
#
# ⚠️ **文字で答えさせない。** 「none」と打たれると、その文字が
#    そのまま Note に足されて記録に残ってしまった。
MEDIA_YES = "media:yes"
MEDIA_NO = "media:no"


class _SkipAI(Exception):
    """source="ai" の項目が無いモードで要約を飛ばすための印。"""

# 裏で走らせたタスクの参照を持っておく。
# 持たないとガベージコレクタに回収されて途中で止まりうる
_background: set = set()

TEXTS: Dict[str, Dict[str, str]] = {
    "saved": {"en": "Saved. Thank you.", "km": "បានរក្សាទុក។ អរគុណ។"},
    "save_failed": {"en": "Could not save. Please try again.", "km": "មិនអាចរក្សាទុកបានទេ។ សូមព្យាយាមម្តងទៀត។"},
    "in_progress": {"en": "Still saving. Please wait.", "km": "កំពុងរក្សាទុក។ សូមរង់ចាំ។"},
    "keep_going": {"en": "Please tell me more.", "km": "សូមប្រាប់ខ្ញុំបន្ថែម។"},
    "no_session": {"en": "Please choose what to record with /start", "km": "សូមជ្រើសរើសអ្វីដែលត្រូវកត់ត្រាដោយប្រើ /start"},
    "btn_save": {"en": "Save", "km": "រក្សាទុក"},
    "btn_more": {"en": "Add more", "km": "បន្ថែមទៀត"},
    "btn_yes": {"en": "Yes", "km": "បាទ/ចាស"},
    "btn_no": {"en": "No", "km": "ទេ"},
    # 文字起こしが裏で走っている間に確認カードを見た時。
    # 本文がまだ入っていないので、空の記録に見えてしまう
    "transcribing": {
        "en": "(Your voice message is still being written down. It will be included.)",
        "km": "(សារជាសំឡេងរបស់អ្នកកំពុងត្រូវបានសរសេរចុះ។ វានឹងត្រូវបានបញ្ចូល។)",
    },
    "send_media": {
        "en": "Please send the photo or video now.",
        "km": "សូមផ្ញើរូបថត ឬវីដេអូឥឡូវនេះ។",
    },
    "media_failed": {"en": "Could not read that file.", "km": "មិនអាចអានឯកសារនោះបានទេ។"},
    "confirm_head": {"en": "Is this correct?", "km": "តើនេះត្រឹមត្រូវទេ?"},
    # 打ち込んだ直後に必ず出す。LLMに5〜10秒、音声の文字起こしには
    # 50秒かかるので、何も出ないと先生は待っているのか分からない。
    # 返信を送る直前に消す
    "thinking": {
        "en": "Thinking...",
        "km": "កំពុងគិត...",
    },
    # 保存の直前に1回だけ聞く。写真や動画が1つも無い時
    "ask_media": {
        "en": "Do you have any photos or videos to add?",
        "km": "តើអ្នកមានរូបថត ឬវីដេអូដែលត្រូវបញ្ចូលទេ?",
    },
    # 保存が裏で失敗した時。セッションは残すのでもう一度押せる
    "save_failed_later": {
        "en": "Sorry, saving failed. Please press Save again.",
        "km": "សុំទោស ការរក្សាទុកបរាជ័យ។ សូមចុច Save ម្តងទៀត។",
    },
}


def t(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en}\n{km}" if km else en


def _btn(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en} / {km}" if km else en


def _filled(route: str, telegram_id: int) -> Dict[str, Any]:
    return (session.get_session(route, telegram_id) or {}).get("filled", {})


def _static_question(
    fields: List[flow.Field], filled: Dict[str, Any]
) -> str:
    """schema.py に書いた固定の質問を英語とクメール語で返す。

    LLMを使わない。モードに入った1回目と、LLMが落ちた時に使う。
    """
    field = flow.next_field(fields, filled)
    if field is None:
        return ""
    en = (field.get("question") or "").strip()
    km = (field.get("question_km") or "").strip()
    return f"{en}\n{km}" if km else en


# 写真・動画を聞いたことを覚えておく印（session の pending に入れる）
MEDIA_ASKED = "media_asked"


def _should_ask_media(
    route: str,
    telegram_id: int,
    fields: List[flow.Field],
    filled: Dict[str, Any],
) -> bool:
    """写真・動画を聞くべきか。

    1回だけ聞く。聞いたことは pending に残す（session を消すまで残る）。
    写真でも動画でも1つでも入っていれば聞かない。
    media の項目が無いモード（探究テーマ）では聞かない。
    """
    kinds = {
        f.get("media_kind")
        for f in fields
        if f.get("source") == "media"
    }
    if not ({"photo", "video"} & kinds):
        return False

    if session.get_pending(route, telegram_id) == MEDIA_ASKED:
        return False

    for f in fields:
        if f.get("source") == "media" and f.get("media_kind") in ("photo", "video"):
            if filled.get(f["key"]):
                return False
    return True


async def _thinking(inc: Incoming, route: str) -> Optional[int]:
    """「Thinking...」を出す。message_id を返す。

    打ち込んだ直後に必ず呼ぶ。LLMに5〜10秒、音声には50秒かかるので、
    何も出ないと先生は待っているのか分からない。

    ⚠️ 既に出していれば送り直さない。写真を複数枚送ると Telegram が
    1枚ずつ別メッセージで送ってくるので、**Thinking が枚数分出る**
    （2026-10-13に実機で発生）。
    """
    existing = session.get_notice(route, inc.telegram_id)
    if existing:
        return existing

    # ⚠️ 原子的に取る。テキストを続けて打つと並行処理で両方が
    # 「まだ出ていない」を読んでしまう
    if not session.acquire_lock("thinking", inc.telegram_id, ttl=600):
        return session.get_notice(route, inc.telegram_id)

    mid = await telegram.send_message(inc.chat_id, t("thinking"))
    if mid:
        session.set_notice(route, inc.telegram_id, mid)
    log.info("[8] Thinking を送った message_id=%s", mid)
    return mid


async def _reply(
    inc: Incoming,
    notice_id: Optional[int],
    text: str,
    *,
    reply_markup: Optional[dict] = None,
    route: str = "",
) -> None:
    """「Thinking...」を消してから返信する。

    ⚠️ 書き換え（editMessageText）ではなく削除にしている。
    編集では**通知が飛ばない。** 音声で50秒待つ間に先生がアプリを
    離れていると返信に気づけない。消して送り直せば通知が鳴る。
    """
    if notice_id:
        await telegram.delete_message(inc.chat_id, notice_id)
        if route:
            session.clear_notice(route, inc.telegram_id)
        # 次のメッセージで Thinking を出せるように鍵を返す
        session.release_lock("thinking", inc.telegram_id)
    await telegram.send_message(inc.chat_id, text, reply_markup=reply_markup)


# 一覧やカードに並べる欄の長さ。音声は50秒で数百文字になるので、
# そのまま入れると Compare your comments で2件を見比べられない
VERBATIM_MAX = 150
ELLIPSIS = "…"


# 足していくときの区切り。Notionでも段落として見える
SEP_NOTE = "\n\n"


def _appended(before: Any, text: str) -> str:
    """同じ項目に発話を足していく。

    ⚠️ **上書きしない。** 上書きだと Add more を繰り返したときに
    最後の発話だけが残り、先生が話した内容が消える
    （2026-10-17 先方から指摘）。

    1回目はそのまま。2回目以降は空行を挟んで繋ぐ。
    """
    head = str(before or "").strip()
    tail = (text or "").strip()
    if not head:
        return tail
    if not tail:
        return head
    return f"{head}{SEP_NOTE}{tail}"


def clip_for_display(text: str) -> str:
    """一覧やカードに並べるときだけ短くする。150文字＋「…」。

    ⚠️ **保存するときには切らない**（2026-10-21変更）。
    ご指示は「元のデータベースの文字数は変えずに、表示だけ点点点」
    （2026-10-13）だったが、保存時に切っていたので食い違っていた。

    さらに `accumulate` で発話を足していく形にしたため、保存時に切ると
    **2回目以降の発話が見えなくなる。** Notion には全文を入れ、
    読み比べのカードに出すときだけここで短くする。
    """
    text = (text or "").strip()
    if len(text) <= VERBATIM_MAX:
        return text
    return text[:VERBATIM_MAX].rstrip() + ELLIPSIS


def _fill_if_present(
    route: str, telegram_id: int, fields: List[flow.Field], values: Dict[str, Any]
) -> None:
    """schema にある key だけ入れる。持っていないモードでは何もしない。"""
    keys = {f["key"] for f in fields}
    session.update_filled(
        route, telegram_id, {k: v for k, v in values.items() if k in keys and v}
    )


def _append_if_present(
    route: str, telegram_id: int, fields: List[flow.Field], values: Dict[str, Any]
) -> None:
    """schema にある key に**足していく。** 上書きしない。

    ⚠️ 音声を複数通送ると、1通ごとに中身が違う。上書きだと
    **最後の1通の文字起こしだけが残る**（2026-10-22に発覚）。
    写真はリストに足されるので問題にならなかったが、文字は上書きだった。

    `STT_Km` は全文の控えなので、足すほうが筋が通る
    （2026-10-22 ユーザー判断）。`Translated_En` も同じ理由で足す。
    足さないと、8分類に渡る英訳が**最後の1通の分だけ**になる。
    """
    keys = {f["key"] for f in fields}
    current = _filled(route, telegram_id)
    merged = {
        k: _appended(current.get(k), v)
        for k, v in values.items()
        if k in keys and v
    }
    if merged:
        session.update_filled(route, telegram_id, merged)


def _media_key(fields: List[flow.Field], kind: str) -> Optional[str]:
    """写真を Image、音声を Audio に振り分けるための項目を探す。

    schema.py が source="media" の項目に media_kind を書いておく。
    """
    for f in fields:
        if f.get("source") == "media" and f.get("media_kind") == kind:
            return f["key"]
    return None


def _media_key_for(inc: Incoming, fields: List[flow.Field]) -> Optional[str]:
    """このメディアを入れる項目。

    ⚠️ **音声として送られたものは、送り方に関わらず Audio に入れる**
    （2026-10-21追加）。mp3 を「ファイル」で添付すると
    kind="document" になり、授業研究には document 用の項目が無いので
    **R2 にも Notion にも残らなかった。**

    音声ファイルは残す必要がある（2026-10-21 ユーザー判断）ので、
    document で中身が音声なら voice の項目を使う。
    """
    key = _media_key(fields, inc.kind)
    if key:
        return key
    if _is_audio(inc):
        return _media_key(fields, "voice")
    return None


def _is_audio(inc: Incoming) -> bool:
    """文字起こしの対象かどうか。

    ⚠️ **「ファイル」として送られた音声も対象にする**（2026-10-21追加）。
    dispatcher は Telegram の `voice` と `audio` を kind="voice" に寄せるが、
    **mp3 を「ファイル」で添付すると kind="document" になる。**
    以前は document を素通りさせていたので、R2に上がるだけで
    **文字起こしも分類もされなかった。**
    """
    if inc.kind == "voice":
        return True
    if inc.kind != "document":
        return False
    return (inc.mime_type or "").split(";")[0].strip().lower().startswith("audio/")


async def _store_media(inc: Incoming, fields: List[flow.Field], route: str) -> str:
    """メディアをR2に上げる。音声なら文字起こしして本文を返す。

    返すのは「本文として扱うテキスト」。音声なら**クメール語の文字起こし**、
    それ以外は caption（無ければ空）。

    ⚠️ 英訳を返してはいけない。history に英語が積まれ、ask.py が
    クメール語の先生に英語で返すようになる（2026-10-13に実機で発生）。
    英訳は translated_en に入れてあり、分類がそこを見る。
    """
    url = await telegram.get_file_url(inc.file_id)

    key = _media_key_for(inc, fields)
    if key:
        try:
            public_url = await media.upload_from_url(
                url,
                app=route,
                telegram_id=inc.telegram_id,
                kind=inc.kind,
                content_type=inc.mime_type,
            )
            # 同じ項目に複数送れるよう、リストに足す
            current = _filled(route, inc.telegram_id).get(key) or []
            if not isinstance(current, list):
                current = [current]
            session.update_filled(
                route, inc.telegram_id, {key: current + [public_url]}
            )
        except Exception:
            log.exception("R2へのアップロードに失敗 route=%s", route)

    # ⚠️ **文字起こしはここでやらない**（2026-10-22変更）。
    # 待っていると 50秒の音声で Thinking が50秒出続ける。
    # 呼び出し側が start_transcribe で裏に回す
    return inc.text


# 走っている文字起こし。保存のときに待ち合わせる
_transcribing: Dict[int, Set["asyncio.Task"]] = {}

# 保存の鍵のTTL（秒）。**文字起こしの待ち時間より長くする。**
# 待っている間に切れると、もう一度 Save が押せてNotionに二重で書かれる
# （external_id は update_id から作るので、押し直した分は重複と判定されない）
SAVE_LOCK_TTL = 360

# 文字起こしを待つ上限（秒）。SAVE_LOCK_TTL より短くする。
#
# ⚠️ 100秒では**長い音声の中身が記録に入らなかった**（2026-10-26変更）。
# Geminiは30秒ごとに分けて呼ぶので、呼び出し回数は音声の長さに比例する。
#   10分の音声 → 約20チャンク → 60〜170秒
# 打ち切ると音声ファイルだけが残り、本文が空のまま確定する。
# **全部終わってからNotionに書く**方針にしたので、5分まで待つ
TRANSCRIBE_WAIT = 300


async def _transcribe_later(
    inc: Incoming, fields: List[flow.Field], route: str, accumulate: str
) -> None:
    """音声を**裏で**文字起こしして、本文に足す。

    ⚠️ 終わっても返事はしない。会話はもう先に進んでいる。
    失敗した時だけ先生に伝える。
    """
    url = await telegram.get_file_url(inc.file_id)

    path = ""
    try:
        suffix = media._ext("", inc.mime_type) or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            path = tmp.name
            async with httpx.AsyncClient(timeout=180) as client:
                res = await client.get(url)
                res.raise_for_status()
                tmp.write(res.content)

        km, en = await stt.transcribe(path)
    except Exception:
        log.exception("文字起こしに失敗 route=%s", route)
        km, en = "", ""
    finally:
        if path and os.path.exists(path):
            os.unlink(path)

    if not (km or en):
        await telegram.send_message(inc.chat_id, t("media_failed"))
        return

    # ⚠️ **足す。** 音声を複数通送ると1通ごとに中身が違うので、
    # 上書きだと最後の1通だけが残る（2026-10-22に発覚）
    #
    # ⚠️ `audio_stt_org` が新しい宛先（2026-10-26）。旧キーも渡し続けるが、
    # **schema から外したモードでは _append_if_present が捨てる。**
    # だから授業研究は audio_stt_org にだけ入り、他モードは何も起きない
    _append_if_present(
        route,
        inc.telegram_id,
        fields,
        {"audio_stt_org": km, "stt_km": km, "translated_en": en},
    )

    text = stt.teacher_text(km, en)
    if text and accumulate:
        current = _filled(route, inc.telegram_id)
        session.update_filled(
            route,
            inc.telegram_id,
            {accumulate: _appended(current.get(accumulate), text)},
        )
        session.append_history(route, inc.telegram_id, "user", text)

    log.info("裏で文字起こしを足した route=%s %d文字", route, len(text))


def start_transcribe(
    inc: Incoming, fields: List[flow.Field], route: str, accumulate: str
) -> None:
    """文字起こしを裏で始める。保存のときに待ち合わせられるよう登録する。"""
    task = asyncio.create_task(
        _transcribe_later(inc, fields, route, accumulate)
    )
    _transcribing.setdefault(inc.telegram_id, set()).add(task)
    task.add_done_callback(
        lambda t: _transcribing.get(inc.telegram_id, set()).discard(t)
    )


def transcribing_count(telegram_id: int) -> int:
    return len(_transcribing.get(telegram_id) or ())


async def wait_transcribing(telegram_id: int) -> None:
    """走っている文字起こしを待つ。**Notionに書く前に呼ぶ。**

    ⚠️ ここを飛ばすと、文字起こしが終わる前にNotionへ書き込み、
    **音声の中身が入らないまま記録が確定する**（セッションも消えるので
    あとから足すこともできない）。

    上限を置くのは、終わらない処理で保存が止まらないようにするため。
    超えたら音声なしで書く。記録が残らないより良い。
    """
    tasks = set(_transcribing.get(telegram_id) or ())
    if not tasks:
        return

    log.info("文字起こしの完了を待つ: %d件", len(tasks))
    done, pending = await asyncio.wait(tasks, timeout=TRANSCRIBE_WAIT)
    if pending:
        log.warning(
            "文字起こしが %d秒で終わらなかった: %d件。音声なしで保存する",
            TRANSCRIBE_WAIT, len(pending),
        )


# Slackに添付するメディアの種類。**音声は入れない。**
# 50秒の音声が並ぶとスタッフが全部聞くことになり、中身は本文の
# 要約に出ている（2026-10-13 ユーザー判断）
SLACK_MEDIA_KEYS = ("image", "video")


async def _slack_media(sent: Dict[str, str], filled: Dict[str, Any]) -> None:
    """投稿したメッセージのスレッドに、画像と動画を付ける。

    ⚠️ 本体のメッセージと**同じスレッドに入れる**（thread_ts）。
    チャンネル直下に並べると、1件の記録で写真の枚数ぶん
    メッセージが増えてチャンネルが流れる。

    R2の公開URLしか手元に無いので、一度ダウンロードして上げ直す。
    失敗しても例外にしない（Slackは通知で、正本はNotion）。
    """
    urls: List[str] = []
    for key in SLACK_MEDIA_KEYS:
        value = filled.get(key) or []
        if not isinstance(value, list):
            value = [value]
        urls.extend(str(v) for v in value if v)

    if not urls:
        return

    items: List[Any] = []
    for url in urls:
        try:
            items.append((url.rsplit("/", 1)[-1], await slack.fetch(url)))
        except Exception as e:
            log.warning("Slackに上げる前のダウンロードに失敗: %s", e)

    if not items:
        return

    count = await slack.upload(
        sent.get("channel", ""), items, thread_ts=sent.get("ts", "")
    )
    log.info("Slackに添付した: %d / %d", count, len(items))


async def handle(
    inc: Incoming,
    user: Dict[str, Any],
    *,
    route: str,
    fields: List[flow.Field],
    db_id: str,
    post_to_slack: bool = False,
    # Slackの1行目を作る関数。(user, filled) -> str。
    # 渡さなければ「<名前> has put the record!」になる
    slack_head: Optional[Callable] = None,
    before_save: Optional[Callable] = None,
    after_save: Optional[Callable] = None,
    use_llm: bool = True,
    followup: bool = True,
    accumulate: str = "",
) -> None:
    """3モードが共有する会話ループ。

    各モードの handler.py は route / fields / db_id を埋めて
    これを呼ぶだけにする。
    """
    log.info(
        "[7] base.handle route=%s kind=%s text=%r media=%s callback=%s",
        route, inc.kind, (inc.text or "")[:40], inc.has_media, inc.is_callback,
    )

    if session.get_session(route, inc.telegram_id) is None:
        log.info("セッションが無い route=%s", route)
        await telegram.send_message(inc.chat_id, t("no_session"))
        session.clear_route(inc.telegram_id)
        return

    # --- ボタン ---
    if inc.is_callback:
        # ⚠️ **ボタンのメッセージは消さない**（2026-10-21決定）。
        # 「はい」を押し間違えた先生が、あとで「いいえ」を押して
        # 先へ進めるようにしておく。
        if inc.text == MEDIA_YES:
            await telegram.send_message(inc.chat_id, t("send_media"))
            return
        if inc.text == MEDIA_NO:
            await _confirm(
                inc, route, fields, _filled(route, inc.telegram_id)
            )
            return

        if inc.text == SAVE:
            # ⚠️ before_save / after_save を必ず渡す。
            # 渡し忘れると、モード固有の処理が全部動かない
            # （2026-10-13に実機で発覚）:
            #   探究テーマ  Is Current が立たず、マイページも更新されない
            #   実践例      Subject の照合と Materials のタグが付かない
            #   授業研究    8分類（Category）が入らない
            await _save(
                inc, user,
                route=route, fields=fields, db_id=db_id,
                post_to_slack=post_to_slack,
                slack_head=slack_head,
                before_save=before_save,
                after_save=after_save,
            )
        elif inc.text == MORE:
            await telegram.send_message(inc.chat_id, t("keep_going"))
        return

    # --- メディア / テキスト ---
    #
    # ⚠️ 音声の文字起こしは50秒かかる。何も出さないと先生から見て
    # 無反応になるので、受けた瞬間に一言返して、そのメッセージを
    # 最後に問いかけで書き換える（メッセージを増やさない）
    text = inc.text

    # モードに入った直後（まだ何も書いていない）。
    # ⚠️ ここでLLMを呼ばない。会話が無いので適応する材料が無く、
    # schema.py の固定の質問と変わらない。10秒待たせる意味がない
    if not text and not inc.has_media:
        opening = _static_question(fields, _filled(route, inc.telegram_id))
        if opening:
            session.append_history(route, inc.telegram_id, "assistant", opening)
            await telegram.send_message(inc.chat_id, opening)
        return

    # ⚠️ 写真を複数枚送ると1枚ずつ別メッセージで届き、**並行して処理される。**
    # Thinking を出す前に鍵を取らないと、両方が「まだ出ていない」を読んで
    # 2つ出る（2026-10-13に実機で発生）。
    # 鍵は原子的なので、必ず1つだけが先に進む
    if inc.has_media:
        got_turn = session.acquire_lock("media_reply", inc.telegram_id, ttl=8)

        # ⚠️ **音声は待たない**（2026-10-22変更）。文字起こしは裏に回し、
        # 会話だけ先に進める。以前は完了を待っていたので、50秒の音声で
        # **Thinking が50秒出続けていた。**
        #
        # 取りこぼさない仕組み: 保存は「Saved」を先に返してNotionへの
        # 書き込みを裏でやるので、そこで wait_transcribing() が待つ
        if _is_audio(inc):
            await _store_media(inc, fields, route)       # R2 に残す
            start_transcribe(inc, fields, route, accumulate)

            if got_turn:
                # ⚠️ **写真の有無だけを聞く**（2026-10-22決定）。
                # 深掘りの固定文も一緒に出していたが、2つ並ぶと
                # 何に答えればよいか分からない。
                # 本文がまだ無いので、内容に触れた深掘りは作れない
                filled = _filled(route, inc.telegram_id)
                if _should_ask_media(route, inc.telegram_id, fields, filled):
                    session.set_pending(route, inc.telegram_id, MEDIA_ASKED)
                    question = t("ask_media")
                    rows = [
                        [(_btn("btn_yes"), MEDIA_YES), (_btn("btn_no"), MEDIA_NO)]
                    ]
                else:
                    # 写真はもう聞いた（または聞く項目が無い）。
                    # 深掘りの固定文を出して、保存もできるようにする。
                    #
                    # ⚠️ Add more も出す（2026-10-22 ユーザー要望）。
                    # Save だけだと「まだ話したいことがある」先生の行き先が無い
                    question = f"{ask.FOLLOWUP_EN}\n{ask.FOLLOWUP_KM}"
                    session.append_history(
                        route, inc.telegram_id, "assistant", question
                    )
                    rows = [
                        [(_btn("btn_save"), SAVE), (_btn("btn_more"), MORE)]
                    ]

                await telegram.send_message(
                    inc.chat_id,
                    question,
                    reply_markup=telegram.inline_keyboard(rows),
                )
            return

        if not got_turn:
            # 同じ束の2枚目以降。**保存はするが返事はしない**
            await _store_media(inc, fields, route)
            log.info("同じ束の2枚目以降。返事はしない")
            return

    notice_id = await _thinking(inc, route)

    async with telegram.typing(inc.chat_id):
        if inc.has_media:
            text = await _store_media(inc, fields, route)

        if text:
            session.append_history(route, inc.telegram_id, "user", text)

            if not use_llm:
                # ⚠️ 設定するだけのモード（探究テーマ）はLLMを使わない。
                # 打った文がそのまま答えなので、抽出するものが無い。
                # 1回のLLM呼び出しで5〜10秒待たせる理由が無い

                current = _filled(route, inc.telegram_id)

                if accumulate:
                    session.update_filled(
                        route,
                        inc.telegram_id,
                        {accumulate: _appended(current.get(accumulate), text)},
                    )
                    # ⚠️ **打ち込みと caption は text_org にも積む**
                    # （2026-10-26）。accumulate の宛先には音声も混ざるので、
                    # 「打ち込みだけ」を取り出せる場所を別に持つ。
                    # schema に無いモードでは捨てられる
                    _append_if_present(
                        route, inc.telegram_id, fields, {"text_org": text}
                    )
                else:
                    # accumulate を渡していないモード（探究テーマ）。
                    # 答えは1つなので、そのまま入れる
                    field = flow.next_field(fields, filled=current)
                    if field is not None:
                        session.update_filled(
                            route, inc.telegram_id, {field["key"]: text}
                        )
            else:
                try:
                    values = await extract.extract_values(
                        fields, session.get_history(route, inc.telegram_id), text
                    )
                    session.update_filled(route, inc.telegram_id, values)
                except Exception:
                    log.exception("抽出に失敗 route=%s", route)

        filled = _filled(route, inc.telegram_id)


        # --- 次の問いかけ ---
        ask_count = (session.get_session(route, inc.telegram_id) or {}).get(
            "ask_count", 0
        )
        # ⚠️ followup=False は「LLMの深掘りをしない」モード（授業研究）。
        # schema.py の固定の質問は下のフォールバックで出るので、
        # 未充足のまま確認カードに飛ぶことはない
        skip_ask = not followup
        question = None if skip_ask else await ask.make_question(
            fields,
            filled,
            session.get_history(route, inc.telegram_id),
            ask_count,
            # 直前に来たものの種類で問いかけ方を変える（2026-10-13）
            kind=inc.kind,
        )

        # ⚠️ make_question の None は「掘り下げを使い切った」と
        # 「LLMが落ちた」の両方で返る。区別できないので充足を確かめる。
        # 未充足なら schema.py の固定の質問に落とす（proposal §4-6）
        #
        # ⚠️ **文字起こし中は聞き直さない**（2026-10-26追加）。本文は
        # これから入るので、聞き直しても先生は答えようがない。
        #   5分の音声 → [写真はありますか] → [Yes] → 写真を送る
        #   → text も audio_stt も空 → **同じ質問が延々と繰り返され、
        #     文字起こしが終わるまで Save に到達できなかった**
        # 確認カードは本文が空の場合に対応済み（_confirm が
        # 「文字起こし中」を添える）。保存時に wait_transcribing() が
        # 待つので内容は欠けない
        if (
            not question
            and not flow.is_complete(fields, filled)
            and not transcribing_count(inc.telegram_id)
        ):
            question = _static_question(fields, filled)
            if question:
                session.append_history(
                    route, inc.telegram_id, "assistant", question
                )
                await _reply(inc, notice_id, question, route=route)
                return

        if question:
            session.bump_ask_count(route, inc.telegram_id)
            session.append_history(route, inc.telegram_id, "assistant", question)
            await _reply(inc, notice_id, question, route=route)
            return

    # ⚠️ 確認カードの手前で、写真や動画が1つも無ければ1回だけ聞く
    # （2026-10-13決定）。先生は口頭で話すと写真を忘れる
    if _should_ask_media(route, inc.telegram_id, fields, filled):
        session.set_pending(route, inc.telegram_id, MEDIA_ASKED)
        # ⚠️ **ボタンで聞く**（2026-10-21変更）。文字で答えさせると
        # 「none」が Note に足されて記録に残った
        rows = [[(_btn("btn_yes"), MEDIA_YES), (_btn("btn_no"), MEDIA_NO)]]
        await _reply(
            inc,
            notice_id,
            t("ask_media"),
            reply_markup=telegram.inline_keyboard(rows),
            route=route,
        )
        return

    await _confirm(inc, route, fields, filled, notice_id)


async def _confirm(
    inc: Incoming,
    route: str,
    fields: List[flow.Field],
    filled: Dict[str, Any],
    notice_id: Optional[int] = None,
) -> None:
    # ⚠️ 本文が空のこともある（音声の文字起こしが裏で走っている間）。
    # 空の行を並べないよう、ある部分だけを繋ぐ
    parts = [t("confirm_head")]

    body = flow.render_confirmation(fields, filled)
    if body:
        parts.append(body)

    # 一言添えないと「記録に失敗した」ように見える（2026-10-22）
    if transcribing_count(inc.telegram_id):
        parts.append(t("transcribing"))

    rows = [[(_btn("btn_save"), SAVE), (_btn("btn_more"), MORE)]]
    await _reply(
        inc,
        notice_id,
        "\n\n".join(parts),
        reply_markup=telegram.inline_keyboard(rows),
        route=route,
    )


async def _save(
    inc: Incoming,
    user: Dict[str, Any],
    *,
    route: str,
    fields: List[flow.Field],
    db_id: str,
    post_to_slack: bool,
    slack_head: Optional[Callable] = None,
    before_save: Optional[Callable] = None,
    after_save: Optional[Callable] = None,
) -> None:
    """保存する。**先生にはすぐ「保存しました」を返し、処理は裏で走らせる。**

    Notionへの書き込み・要約のLLM・Slack投稿で合わせて15秒ほどかかる。
    先生を待たせる理由が無い（2026-10-13決定）。

    連打はここで止める。
    ⚠️ Notionに触る前に鍵を取る。clear_session だけでは、
    ほぼ同時の2タップが両方「セッションあり」を読んでしまう
    """
    # ⚠️ TTL は文字起こしの待ち時間より長くする（SAVE_LOCK_TTL）。
    # 待っている間に切れると、もう一度 Save が押せてNotionに二重で書かれる
    if not session.acquire_lock("save", inc.telegram_id, ttl=SAVE_LOCK_TTL):
        await telegram.send_message(inc.chat_id, t("in_progress"))
        return

    if session.get_session(route, inc.telegram_id) is None:
        session.release_lock("save", inc.telegram_id)
        return

    # --- 先生にはここで返す ---
    filled = _filled(route, inc.telegram_id)

    # ⚠️ 文字起こしが走っている間は**中身を出さない。** まだ本文が
    # 入っていないので、出すと「空の記録が保存された」ように見える。
    # Notionには wait_transcribing() のあとで完全なものが入る
    if transcribing_count(inc.telegram_id):
        done = t("saved")
    else:
        done = f"{t('saved')}\n\n{flow.render_confirmation(fields, filled)}"
    if inc.message_id:
        # 押したボタンを消す。あとから押し直せないように
        await telegram.edit_message_text(inc.chat_id, inc.message_id, done)
    else:
        await telegram.send_message(inc.chat_id, done)

    # --- 残りは裏で ---
    task = asyncio.create_task(
        _save_background(
            inc, user,
            route=route, fields=fields, db_id=db_id,
            post_to_slack=post_to_slack,
            slack_head=slack_head,
            before_save=before_save, after_save=after_save,
        )
    )
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _save_background(
    inc: Incoming,
    user: Dict[str, Any],
    *,
    route: str,
    fields: List[flow.Field],
    db_id: str,
    post_to_slack: bool,
    slack_head: Optional[Callable] = None,
    before_save: Optional[Callable] = None,
    after_save: Optional[Callable] = None,
) -> None:
    """保存の本体。裏で走る。

    ⚠️ 失敗したらセッションを消さない。先生がもう一度
    保存ボタンを押せるようにするため。「保存しました」と伝えた後に
    失敗したので、**必ず伝える。**
    """
    try:
        # ⚠️ **文字起こしの完了を待つ。** 先生はもう「Saved」を受け取って
        # いるので、ここで待っても待たせていない。飛ばすと
        # **音声の中身が入らないまま記録が確定する**（2026-10-22）
        await wait_transcribing(inc.telegram_id)

        # 自動で入る項目
        _fill_if_present(route, inc.telegram_id, fields, {
            "date": date.today().isoformat(),
            "teacher": user.get("notion_page_id"),
            "school": user.get("school_id"),
            "external_id": notion_writer.make_external_id(inc.update_id),
        })

        if before_save:
            try:
                await before_save(inc, user)
            except Exception:
                log.exception("before_save に失敗 route=%s", route)

        # AIが埋める項目。
        # ⚠️ source="ai" の項目が1つも無いモード（探究テーマ）では呼ばない。
        # 呼んでも _fill_if_present が捨てるだけで、LLMを2回無駄に叩く
        filled = _filled(route, inc.telegram_id)
        has_ai = any(f.get("source") == "ai" for f in fields)
        try:
            if not has_ai:
                raise _SkipAI
            title = await summarize.make_summary(fields, filled)
            keywords = await summarize.make_keywords(
                flow.render_confirmation(fields, filled)
            )
            _fill_if_present(route, inc.telegram_id, fields, {
                "summary": title, "title": title, "keywords": keywords,
            })
        except _SkipAI:
            pass
        except Exception:
            log.exception("要約に失敗 route=%s", route)

        filled = _filled(route, inc.telegram_id)
        page_id = await notion_writer.save(db_id, fields, filled)
        log.info("保存した route=%s page=%s", route, page_id)

        # モード固有の後処理（探究テーマならマイページの見出しを直す）。
        # ⚠️ ここより前に置くとNotionにまだページが無く、
        # current_rq() が見つけられない
        if after_save:
            try:
                await after_save(inc, user, page_id)
            except Exception:
                log.exception("after_save に失敗 route=%s", route)

        if post_to_slack:
            try:
                head = slack_head(user, filled) if slack_head else ""
                text = await summarize.make_slack_text(
                    user.get("name", ""), fields, filled, head=head
                )
                if text:
                    sent = await slack.post(
                        text, school_id=user.get("school_id", "")
                    )
                    if sent:
                        await _slack_media(sent, filled)
            except Exception:
                log.exception("Slack投稿に失敗")

        session.clear_session(route, inc.telegram_id)

    except Exception:
        log.exception("保存に失敗 route=%s", route)
        # セッションは残す。もう一度押せるように
        await telegram.send_message(inc.chat_id, t("save_failed_later"))
    finally:
        session.release_lock("save", inc.telegram_id)
