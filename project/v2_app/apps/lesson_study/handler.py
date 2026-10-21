"""授業研究コメントの入口。

他のモードと違う点が2つ:
  ① 会話の前に「どの授業研究か」を一覧から選ばせる
  ② 保存の直前に8分類を当てる（core/categorize.py）
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any, Dict

from v2_app.apps import base
from v2_app.apps.lesson_study import repo
from v2_app.apps.lesson_study.schema import DB_ID, FIELDS
from v2_app.core import categorize, lang, session, stt_gemini, telegram
from v2_app.router.dispatcher import Incoming

log = logging.getLogger("impactdb.v2")

ROUTE = "lesson_study"
PICK = "ls:"

# filled に入れる作業用のキー。**schema.py の FIELDS には無い。**
# Notionにも確認カードにも出ない（flow は fields しか見ない）
CHOICES = "_ls_names"      # {page_id: 会の名前}
CHOSEN = "_ls_chosen"      # 選ばれた会の名前

# ボタンのラベルの区切り。幅が惜しいので中点の両側は1文字だけ
SEP = " · "

TEXTS: Dict[str, Dict[str, str]] = {
    "pick": {"en": "Which lesson study is this about?", "km": "តើនេះជាការសិក្សាបទបង្រៀនមួយណា?"},
    "none_open": {
        "en": "There is no open lesson study right now. Please ask the staff.",
        "km": "ឥឡូវនេះគ្មានការសិក្សាបទបង្រៀនបើកចំហទេ។ សូមសួរបុគ្គលិក។",
    },
}


def t(key: str) -> str:
    pair = TEXTS.get(key, {})
    en, km = pair.get("en", ""), pair.get("km", "")
    return f"{en}\n{km}" if km else en


async def _show_list(inc: Incoming) -> None:
    """授業研究の一覧をボタンで出す。

    ⚠️ **Notionに問い合わせるので先に Thinking を出す。** Redisには
    無いデータなので1〜2秒かかる。モードを押した直後に何も出ないと
    先生は反応していないと思って押し直す（2026-10-13 ユーザー要望）。
    """
    notice_id = await base._thinking(inc, ROUTE)

    async with telegram.typing(inc.chat_id):
        studies = await repo.open_lesson_studies()

    if not studies:
        await base._reply(inc, notice_id, t("none_open"), route=ROUTE)
        session.clear_session(ROUTE, inc.telegram_id)
        return

    # 名前・日付・学校を**ボタンのラベルに全部入れる**
    # （2026-10-13 ユーザー要望）。本文は問いかけだけ
    rows = []
    names = {}
    for page_id, name, date, school in studies:
        label = SEP.join(x for x in (name, date, school) if x)
        # callback_data は64バイトまで。"ls:" + page_id = 39バイト
        rows.append([(label, f"{PICK}{page_id}")])
        names[page_id] = name

    # ⚠️ 会の名前をここで覚えておく。callback は page_id しか運べないが、
    # Slackには「どの会へのコメントか」を出したい。ここで持たないと
    # 保存時にNotionへ問い合わせ直すことになる
    session.update_filled(ROUTE, inc.telegram_id, {CHOICES: names})

    await base._reply(
        inc,
        notice_id,
        t("pick"),
        reply_markup=telegram.inline_keyboard(rows),
        route=ROUTE,
    )


def slack_head(user: Dict[str, Any], filled: Dict[str, Any]) -> str:
    """Slackの1行目。**どの会へのコメントかを出す。**

    会の名前は選んだ時点で filled に入れてある（CHOSEN）。
    Notionに問い合わせ直さない。
    """
    name = user.get("name", "A teacher")
    session_name = filled.get(CHOSEN) or ""
    head = f"{name} has put a Lesson Study Reflection"
    return f"{head} on {session_name}" if session_name else head


async def before_save(inc: Incoming, user: Dict[str, Any]) -> None:
    """保存の直前に8分類を当てる。英訳が無ければ先に作る。

    ⚠️ **打ち込みには英訳が無い**（2026-10-21に気づいた）。音声は
    `stt_gemini.run()` が英訳まで作るが、テキストで打った場合は
    `translated_en` が空のまま分類に渡っていた。V1の分類器は
    英語の例文を埋め込んでいるので、原文（クメール語・日本語）を
    渡すと精度が落ちる。

    英語で打った場合は訳さない（訳す意味が無い）。
    """
    filled = (session.get_session(ROUTE, inc.telegram_id) or {}).get("filled", {})
    comment = filled.get("comment") or ""
    english = filled.get("translated_en") or ""

    if comment and not english and lang.guess_from_text(comment) != "en":
        try:
            english = await asyncio.to_thread(stt_gemini.translate_to_en, comment)
        except Exception:
            log.exception("打ち込みの英訳に失敗 route=%s", ROUTE)
            english = ""
        if english:
            session.update_filled(
                ROUTE, inc.telegram_id, {"translated_en": english}
            )

    label = await categorize.categorize(comment, text_en=english)
    if label:
        session.update_filled(ROUTE, inc.telegram_id, {"category": label})


async def handle(inc: Incoming, user: Dict[str, Any]) -> None:
    sess = session.get_session(ROUTE, inc.telegram_id)
    if sess is None:
        # base が「/start からやり直してください」を出す
        await base.handle(inc, user, route=ROUTE, fields=FIELDS, db_id=DB_ID)
        return

    # --- まだ授業研究が選ばれていない ---
    if not sess.get("filled", {}).get("lesson_study"):
        if inc.is_callback and inc.text.startswith(PICK):
            page_id = inc.text[len(PICK) :]
            names = sess.get("filled", {}).get(CHOICES, {})
            session.update_filled(
                ROUTE,
                inc.telegram_id,
                {"lesson_study": page_id, CHOSEN: names.get(page_id, "")},
            )

            # 一覧のメッセージごと消す（2026-10-13 ユーザー要望）。
            # ⚠️ 書き換えだとボタンが消えても問いかけの文が残り、
            # 次の質問の上に古い問いかけが積もって読みにくい。
            # どれを選んだかは次の質問に進むことで分かる
            if inc.message_id:
                await telegram.delete_message(inc.chat_id, inc.message_id)

            # 最初の質問に進む。callback のままだと base が
            # 保存ボタンの処理と誤認するので、空のテキストに変える
            await base.handle(
                dataclasses.replace(
                    inc, kind="text", text="", callback_id=None, file_id=None
                ),
                user,
                route=ROUTE,
                fields=FIELDS,
                db_id=DB_ID,
                before_save=before_save,
                post_to_slack=True,
                slack_head=slack_head,
                followup=False,
                use_llm=False,
                accumulate="comment",
            )
            return

        await _show_list(inc)
        return

    # --- 選び終わっている。通常の会話ループ ---
    await base.handle(
        inc,
        user,
        route=ROUTE,
        fields=FIELDS,
        db_id=DB_ID,
        before_save=before_save,
        # 保存後にSlackへ流す（2026-10-13 ユーザー判断）。
        # 1行目に会の名前と先生の名前、本文はLLMの要約
        post_to_slack=True,
        slack_head=slack_head,
        # LLMの深掘り質問はしない（2026-10-13 ユーザー判断）。
        # 授業研究は会の直後に書くので、聞き返されるより早く終わらせたい
        followup=False,
        # ⚠️ 抽出も通さない。音声が多いモードなのに、抽出のプロンプトは
        # 「短くまとめる」「明確に述べていなければ null」なので、
        # **文字起こしが Comment に入らなかった**（2026-10-13に発覚）。
        # 答える欄は Comment の1つだけなので、言ったことをそのまま入れる
        use_llm=False,
        # ⚠️ **足していく。** 渡していなかったので、2回目以降の発話が
        # どこにも保存されず**消えていた**（2026-10-21に発覚）。
        # comment は required なので、1回目で埋まると flow.next_field が
        # None を返し、保存先が無くなる
        accumulate="comment",
    )
