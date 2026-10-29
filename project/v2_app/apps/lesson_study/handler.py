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
    """保存の直前に、蓄積された原文を英訳して8分類を当てる。

    ⚠️ **英訳は `comment_org` の全文から1回だけ作る**（2026-10-26変更）。
    以前は音声1本ごとに `stt_gemini.run()` が英訳し、それを
    `translated_en` に積んでいた。そのため

      1. 🔴 音声を1本でも送ると、以降の**打ち込みが分類に届かなかった**
         （`not english` のガードで英訳を飛ばしていた）
      2. 音声が複数あると Gemini を本数分呼んでいた

    いまは打ち込みも音声も `comment_org` に積まれているので、
    **そこを1回訳せば全部が分類に渡る。**

    ⚠️ **全部英語なら訳さない。** `lang.guess_from_text` は文字種を
    数えるだけで**LLMを使わない**ので、判定のコストがゼロ。
    訳すと言い換えが入り、埋め込みの近傍が変わる。

    ⚠️ **失敗したら原文をそのまま `comment_eng` に入れる。**
    `Comment_eng` はカテゴライズの入力であり、英語でないほうがマシで
    空は駄目（分類は原文でも動く。精度は落ちる）。
    """
    filled = (session.get_session(ROUTE, inc.telegram_id) or {}).get("filled", {})
    original = filled.get("comment_org") or ""
    if not original:
        return

    if lang.guess_from_text(original) == "en":
        english = original
    else:
        try:
            english = await asyncio.to_thread(stt_gemini.translate_to_en, original)
        except Exception:
            log.exception("英訳に失敗 route=%s", ROUTE)
            english = ""

    analysis = english or original
    session.update_filled(ROUTE, inc.telegram_id, {"comment_eng": analysis})

    # ⚠️ **分類されるのは `text_en`**（= analysis）。第1引数は
    # `text_en` が空のときの翻訳元としてしか使われない（categorize.py:52
    # の `english = text_en or await to_english(text)`）。
    # analysis は必ず埋まるので、いまは第1引数は使われない
    label = await categorize.categorize(original, text_en=analysis)
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
                accumulate="comment_org",
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
        # 答える欄は1つだけなので、言ったことをそのまま入れる
        use_llm=False,
        # ⚠️ **足していく。** 渡していなかったので、2回目以降の発話が
        # どこにも保存されず**消えていた**（2026-10-21に発覚）。
        # comment_org は required なので、1回目で埋まると flow.next_field が
        # None を返し、保存先が無くなる。
        #
        # ⚠️ **ここが「全部入る」場所**（2026-10-26）。打ち込み・音声・caption が
        # すべて comment_org に積まれる。base.py が並行して text_org /
        # audio_stt_org にも振り分ける
        accumulate="comment_org",
    )
