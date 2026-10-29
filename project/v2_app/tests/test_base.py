"""base.py の小さな関数。通信なし。

会話ループ本体は実機で見るしかないが、文字を切る判断だけは
「消してはいけない文を消す」事故につながるのでここで止める。
"""

from __future__ import annotations

from v2_app.apps import base
from v2_app.tests.harness import Suite

suite = Suite("base")

LONG = "ក" * 400


@suite.case("表示用: 短い文はそのまま返す")
def _() -> None:
    assert base.clip_for_display("short") == "short"


@suite.case("表示用: 長い文は切って「…」を付ける")
def _() -> None:
    out = base.clip_for_display(LONG)
    assert out.endswith(base.ELLIPSIS), out
    assert len(out) == base.VERBATIM_MAX + 1, len(out)


@suite.case("表示用: ちょうど上限なら切らない")
def _() -> None:
    text = "a" * base.VERBATIM_MAX
    assert base.clip_for_display(text) == text


@suite.case("保存するときは切らない（全文をNotionに入れる）")
def _() -> None:
    """⚠️ 2026-10-21変更。保存時に切ると、足していった2回目以降が
    見えなくなる。切るのは表示だけ（ai_summary.write_comparison）。
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(base.handle))
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "clip_for_display" not in names, "保存の経路で切っている"
    assert not hasattr(base, "_clip"), "_clip が残っている"


@suite.case("1回目はそのまま入る")
def _() -> None:
    assert base._appended(None, "I used group work.") == "I used group work."
    assert base._appended("", "I used group work.") == "I used group work."


@suite.case("2回目は空行を挟んで足される（上書きしない）")
def _() -> None:
    """⚠️ ここが Add more の本体。上書きすると先生の発話が消える。"""
    out = base._appended("I used group work.", "Two quiet boys explained.")
    assert out == "I used group work.\n\nTwo quiet boys explained."


@suite.case("3回繰り返しても全部残る")
def _() -> None:
    out = ""
    for part in ("one", "two", "three"):
        out = base._appended(out, part)
    assert out == "one\n\ntwo\n\nthree", out


@suite.case("空の発話は足さない（写真だけ送られた時）")
def _() -> None:
    assert base._appended("one", "") == "one"
    assert base._appended("one", "   ") == "one"


@suite.case("クメール語を壊さない")
def _() -> None:
    km1, km2 = "ខ្ញុំបានប្រើការងារក្រុម", "សិស្សបានពន្យល់"
    assert base._appended(km1, km2) == f"{km1}\n\n{km2}"


@suite.case("音声は待たずに裏で文字起こしする")
def _() -> None:
    """⚠️ 待っていると50秒の音声で Thinking が50秒出続ける
    （2026-10-22 ユーザー指摘）。会話だけ先に進める。
    """
    import inspect

    import ast

    def called(func) -> set:
        """その関数が呼んでいる名前。コメントや文字列は数えない。"""
        tree = ast.parse(inspect.getsource(func))
        return {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

    in_handle = called(base.handle)
    assert "start_transcribe" in in_handle, "裏に回していない"
    # 待つのは保存のときだけ。会話の経路では待たない
    assert "wait_transcribing" not in in_handle, "会話の経路で待っている"

    assert "wait_transcribing" in called(base._save_background), (
        "保存の前に待っていない"
    )


@suite.case("文字起こしは上書きせず足す（STT_Km / Translated_En）")
def _() -> None:
    """⚠️ 上書きだと最後の1通の文字起こしだけが残る。
    Translated_En も足さないと、8分類に渡る英訳が最後の分だけになる。
    """
    import inspect

    src = inspect.getsource(base._transcribe_later)
    assert "_append_if_present" in src, "上書きしている"
    assert "_fill_if_present(" not in src, "上書きの呼び出しが残っている"


@suite.case("保存の鍵は文字起こしの待ち時間より長い")
def _() -> None:
    """⚠️ 待っている間に鍵が切れると、もう一度 Save が押せて
    **Notionに二重で書かれる**（2026-10-22）。
    """
    assert base.SAVE_LOCK_TTL > base.TRANSCRIBE_WAIT, (
        base.SAVE_LOCK_TTL, base.TRANSCRIBE_WAIT
    )


@suite.case("メディアの有無はボタンで聞く（文字で答えさせない）")
def _() -> None:
    """⚠️ 文字で聞くと「none」が Note に足されて記録に残る
    （2026-10-21 先方から指摘）。
    """
    import ast
    import inspect

    src = inspect.getsource(base.handle)

    # 質問にボタンを付けている
    tree = ast.parse(src)
    asked_with_buttons = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "_reply":
            continue
        args = {a.arg for a in node.keywords}
        if "reply_markup" in args:
            asked_with_buttons = True
    assert asked_with_buttons, "ask_media にボタンが付いていない"

    # 2つの callback を受けている
    assert "MEDIA_YES" in src, "はい を受けていない"
    assert "MEDIA_NO" in src, "いいえ を受けていない"


@suite.case("メディアのボタンの callback_data は64バイト以内")
def _() -> None:
    for value in (base.MEDIA_YES, base.MEDIA_NO, base.SAVE, base.MORE):
        assert len(value.encode()) <= 64, value


@suite.case("発話を足すモードは accumulate を渡している")
def _() -> None:
    """⚠️ 渡し忘れると**2回目以降の発話がどこにも保存されない。**

    required な項目が1回目で埋まると flow.next_field が None を返し、
    保存先が無くなる（2026-10-21に授業研究で発生していた）。
    """
    import inspect

    from v2_app.apps.lesson_study import handler as ls
    from v2_app.apps.reflection import handler as rf

    for name, module, key in (
        ("reflection", rf, '"note"'),
        # 2026-10-26 に comment → comment_org へ改名した
        ("lesson_study", ls, '"comment_org"'),
    ):
        src = inspect.getsource(module)
        assert f"accumulate={key}" in src, f"{name} が accumulate を渡していない"


@suite.case("ファイルで送られた音声も文字起こしの対象になる")
def _() -> None:
    """⚠️ mp3 を「ファイル」で添付すると kind='document' になる。
    素通りさせると R2 に上がるだけで分類もされない（2026-10-21修正）。
    """
    from v2_app.router.dispatcher import Incoming

    def inc(kind, mime=""):
        return Incoming(
            update_id=1, telegram_id=1, chat_id=1, kind=kind, mime_type=mime
        )

    assert base._is_audio(inc("voice"))
    assert base._is_audio(inc("document", "audio/mpeg"))
    assert base._is_audio(inc("document", "audio/ogg; codecs=opus"))
    assert not base._is_audio(inc("document", "application/pdf"))
    assert not base._is_audio(inc("photo", "image/jpeg"))
    assert not base._is_audio(inc("text"))


@suite.case("ファイルで送られた音声も R2 に残る（Audio に入れる）")
def _() -> None:
    """⚠️ 授業研究に document 用の項目が無いので、素通りさせると
    **R2 にも Notion にも残らない**（2026-10-21 ユーザー判断で必須）。
    """
    from v2_app.apps.lesson_study.schema import FIELDS as LS
    from v2_app.apps.reflection.schema import FIELDS as RF
    from v2_app.router.dispatcher import Incoming

    def inc(kind, mime=""):
        return Incoming(
            update_id=1, telegram_id=1, chat_id=1, kind=kind, mime_type=mime
        )

    # 授業研究: document でも音声なら audio（Notion の Audio）に入る
    assert base._media_key_for(inc("document", "audio/mpeg"), LS) == "audio"
    assert base._media_key_for(inc("voice"), LS) == "audio"
    # 音声でない document は入れる先が無い（授業研究には項目が無い）
    assert base._media_key_for(inc("document", "application/pdf"), LS) is None

    # 振り返りは document 用の項目（Files）があるので、そちらが優先される
    assert base._media_key_for(inc("document", "application/pdf"), RF) == "files"
    # 音声でも、document 用の項目がある方が先に当たる
    assert base._media_key_for(inc("document", "audio/mpeg"), RF) == "files"
