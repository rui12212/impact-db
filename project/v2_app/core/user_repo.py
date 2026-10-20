from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from v2_app.core import session
from v2_app.core.config import DB_SCHOOL, DB_SCHOOL_MEMBER, DB_USER
from v2_app.core.notion_client import (
    create_page,
    query_database,
    retrieve_page,
    update_page,
)

DEFAULT_ROLE = "Teacher"

def _title(page: dict, prop: str) -> str:
    items = page.get("properties", {}).get(prop, {}).get("title", [])
    return "".join(i.get("plain_text", "") for i in items)

def _select(page: dict, prop: str) -> Optional[str]:
    sel = page.get("properties", {}).get(prop, {}).get("select")
    return sel.get("name") if sel else None


def _url(page: dict, prop: str) -> str:
    return page.get("properties", {}).get(prop, {}).get("url") or ""

def _text(name: str) -> dict:
    return {"rich_text": [{"text": {"content": name}}]}

# --- User -------------------------------------------------------------
async def find_user(telegram_id: int) -> Optional[dict]:
    """Notion の User を Telegram User ID で探す。見つからなければ None。"""
    res = await query_database(
        DB_USER,
        filter={"property": "Telegram User ID", "number": {"equals": telegram_id}},
        page_size=1,
    )
    results = res.get("results", [])
    return results[0] if results else None

async def create_user(
    telegram_id: int, teacher_name: str, username: str = ""
) -> dict:
    props: Dict[str, Any] = {
        "Teacher Name": {"title": [{"text": {"content": teacher_name or str(telegram_id)}}]},
        "Telegram User ID": {"number": telegram_id},
        "Role": {"select": {"name": DEFAULT_ROLE}},
    }
    if username:
        props["Telegram Username"] = _text(username)
    return await create_page(DB_USER, props)

async def get_or_create_user(
    telegram_id: int, teacher_name: str = "", username: str = ""
) -> Dict[str, Any]:
    """先生の情報を返す。Redis にあればそれを使い、無ければ Notion を見る。

    返す形: {"notion_page_id", "name", "role", "school_id", "school_name"}
    この辞書が user:{telegram_id} の中身そのもの（TTLなし）。
    """
    cached = session.get_user(telegram_id)
    if cached and cached.get("notion_page_id"):
        return cached

    page = await find_user(telegram_id)
    if page is None:
        page = await create_user(telegram_id, teacher_name, username)

    # cached を展開してから上書きする。lang のように Notion に
    # 置き場所が無く Redis が正本の項目を消さないため。
    # 項目を足す時もこのマージを崩さないこと
    data = {
        **(cached or {}),
        "notion_page_id": page["id"],
        "name": _title(page, "Teacher Name"),
        "role": _select(page, "Role") or DEFAULT_ROLE,
        # バッチがマイページのブロックを書き換える先。
        # notion_page_create.py が書き込む（まだ無ければ空）
        "mypage": _url(page, "Mypage"),
        # 設定で選んだ言語。**Notion が正本**（Redis が飛んでも残る）。
        # 空なら Telegram の言語コードに落とす → core/lang.py
        "language": _select(page, "Language") or "",
        "school_id": "",
        "school_name": "",
    }

    member = await get_current_member(page["id"])
    if member:
        school_id, school_name = await _school_of(member)
        data["school_id"] = school_id
        data["school_name"] = school_name

    session.set_user(telegram_id, data)
    return data

# --- School / School Member -------------------------------------------

async def list_schools() -> List[Tuple[str, str]]:
    """(page_id, School Name) の一覧。設定モードで選ばせる用。"""
    res = await query_database(DB_SCHOOL, page_size=100)
    return [(p["id"], _title(p, "School Name")) for p in res.get("results", [])]


async def school_name(school_page_id: str) -> str:
    page = await retrieve_page(school_page_id)
    return _title(page, "School Name")

async def get_current_member(user_page_id: str) -> Optional[dict]:
    """在籍中の School Member レコード。End Date が空のものが在籍中。"""
    res = await query_database(
        DB_SCHOOL_MEMBER,
        filter={
            "and": [
                {"property": "User", "relation": {"contains": user_page_id}},
                {"property": "End Date", "date": {"is_empty": True}},
            ]
        },
        page_size=1,
    )
    results = res.get("results", [])
    return results[0] if results else None

async def _school_of(member: dict) -> Tuple[str, str]:
    rel = member.get("properties", {}).get("School", {}).get("relation", [])
    if not rel:
        return "", ""
    sid = rel[0]["id"]
    return sid, await school_name(sid)


async def set_school(
    telegram_id: int, school_page_id: str, *, name: str = ""
) -> Dict[str, Any]:
    """所属を決める／変える。

    在籍中のレコードがあれば End Date を今日で閉じ、新しいレコードを作る。
    履歴を残すので、過去のデータはその時の学校に紐づいたまま残る。
    """
    user = await get_or_create_user(telegram_id)
    user_page_id = user["notion_page_id"]

    current = await get_current_member(user_page_id)
    if current:
        cur_id, _ = await _school_of(current)
        if cur_id == school_page_id:
            return user
        await update_page(current["id"], {"End Date": {"date": {"start": _today()}}})

    sname = name or await school_name(school_page_id)
    await create_page(
        DB_SCHOOL_MEMBER,
        {
            "Name": {"title": [{"text": {"content": f"{user['name']} - {sname}"}}]},
            "User": {"relation": [{"id": user_page_id}]},
            "School": {"relation": [{"id": school_page_id}]},
            "Start Date": {"date": {"start": _today()}},
        },
    )

    user["school_id"] = school_page_id
    user["school_name"] = sname
    session.set_user(telegram_id, user)
    return user

def _today() -> str:
    return date.today().isoformat()

async def rename(telegram_id: int, new_name: str) -> Dict[str, Any]:
    """先生の表示名を変える。Notion と Redis の両方を直す。

    ⚠️ Redis を直し忘れると、以降の Slack 投稿や返信で古い名前が出続ける。
    """
    user = await get_or_create_user(telegram_id)
    page_id = user.get("notion_page_id")
    if not page_id or not new_name:
        return user

    await update_page(
        page_id,
        {"Teacher Name": {"title": [{"text": {"content": new_name[:2000]}}]}},
    )

    user["name"] = new_name
    session.set_user(telegram_id, user)
    return user


async def set_language(telegram_id: int, lang: str) -> Dict[str, Any]:
    """先生が選んだ言語を変える。Notion と Redis の両方を直す。

    ⚠️ **Notion が正本**（2026-10-20決定）。Redis だけに持つと
    コンテナを止めた時に消え、端末の言語設定に戻ってしまう。

    対応外の言語コードは受け取らない（core/lang.py の SUPPORTED）。
    """
    from v2_app.core import lang as lang_mod

    code = lang_mod.normalize(lang)
    user = await get_or_create_user(telegram_id)
    page_id = user.get("notion_page_id")
    if not page_id or not code:
        return user

    await update_page(page_id, {"Language": {"select": {"name": code}}})

    user["language"] = code
    session.set_user(telegram_id, user)
    return user
