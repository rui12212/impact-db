from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import date
from typing import Any, Dict, List, Optional, Callable

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


def _clip(text: str, filled: Dict[str, Any]) -> str:
    """長い文を VERBATIM_MAX で切って「…」を付ける。

    ⚠️ **全文の控えが STT_Km にある時だけ切る。** 打ち込まれた文は
    そこにしか無いので、切ると消える（2026-10-13 ユーザー要望は
    「元のデータベースの文字数は変えずに表示だけ」）。

    音声・動画は stt.py が STT_Km に全文を入れているので、
    Comment 側は先頭150文字でよい。中身が重複するのは承知の上。
    """
    if len(text) <= VERBATIM_MAX:
        return text
    if not filled.get("stt_km"):
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


def _media_key(fields: List[flow.Field], kind: str) -> Optional[str]:
    """写真を Image、音声を Audio に振り分けるための項目を探す。

    schema.py が source="media" の項目に media_kind を書いておく。
    """
    for f in fields:
        if f.get("source") == "media" and f.get("media_kind") == kind:
            return f["key"]
    return None


async def _store_media(inc: Incoming, fields: List[flow.Field], route: str) -> str:
    """メディアをR2に上げる。音声なら文字起こしして本文を返す。

    返すのは「本文として扱うテキスト」。音声なら**クメール語の文字起こし**、
    それ以外は caption（無ければ空）。

    ⚠️ 英訳を返してはいけない。history に英語が積まれ、ask.py が
    クメール語の先生に英語で返すようになる（2026-10-13に実機で発生）。
    英訳は translated_en に入れてあり、分類がそこを見る。
    """
    url = await telegram.get_file_url(inc.file_id)

    key = _media_key(fields, inc.kind)
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

    if inc.kind != "voice":
        return inc.text

    # V1の core/audio がファイルパスを受ける作りなので、一度落とす
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
        return ""

    _fill_if_present(
        route, inc.telegram_id, fields, {"stt_km": km, "translated_en": en}
    )
    return stt.teacher_text(km, en)


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
        if not session.acquire_lock("media_reply", inc.telegram_id, ttl=8):
            # 同じ束の2枚目以降。**保存はするが返事はしない**
            await _store_media(inc, fields, route)
            log.info("同じ束の2枚目以降。保存だけして返事はしない")
            return

    notice_id = await _thinking(inc, route)

    async with telegram.typing(inc.chat_id):
        if inc.has_media:
            text = await _store_media(inc, fields, route)
            if not text and inc.kind == "voice":
                return

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
                else:
                    field = flow.next_field(fields, filled=current)
                    if field is not None:
                      session.update_filled(
                          route, inc.telegram_id,
                          {field["key"]: _clip(text, current)},
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
        if not question and not flow.is_complete(fields, filled):
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
        await _reply(inc, notice_id, t("ask_media"), route=route)
        return

    await _confirm(inc, route, fields, filled, notice_id)


async def _confirm(
    inc: Incoming,
    route: str,
    fields: List[flow.Field],
    filled: Dict[str, Any],
    notice_id: Optional[int] = None,
) -> None:
    body = flow.render_confirmation(fields, filled)
    rows = [[(_btn("btn_save"), SAVE), (_btn("btn_more"), MORE)]]
    await _reply(
        inc,
        notice_id,
        f"{t('confirm_head')}\n\n{body}",
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
    if not session.acquire_lock("save", inc.telegram_id):
        await telegram.send_message(inc.chat_id, t("in_progress"))
        return

    if session.get_session(route, inc.telegram_id) is None:
        session.release_lock("save", inc.telegram_id)
        return

    # --- 先生にはここで返す ---
    filled = _filled(route, inc.telegram_id)
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
                        text, school_name=user.get("school_name", "")
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
