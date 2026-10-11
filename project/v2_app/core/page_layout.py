"""マイページ・スクールページの構造。

生成スクリプトとバッチの両方が使う。

  scripts/notion_page_create.py  この見出しを書いてページを作る
  batch/keywords.py              この見出しを目印にブロックを探して書き換える
  batch/ai_summary.py            同

⚠️ block_id を保存しない設計。毎回ページを読んで見出しから探す。
   --rebuild でページを作り直してもバッチが追従できるようにするため。
   → dev/2026-10-10.md ステップC

⚠️ 見出しは「英語 · クメール語」で表示するが、**照合は英語部分の
   先頭一致で行う。** クメール語の訳を直しても目印が壊れないようにするため
   （訳は A-9 で先方確認中）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# セクションの見出し。英語側が目印なので**英語は勝手に変えない。**
# クメール語は後から差し替えてよい（照合に使わない）
H_RESEARCH = "Research question for this month"
H_AI_SUMMARY = "AI summary of your learning"
H_DAILY = "Daily reflections"
H_FOCUS = "How your focus has shifted"
H_TIMELINE = "Reflection timeline"
H_LESSON_STUDY = "Lesson study records"
H_SESSIONS = "The sessions"
H_COMPARE = "Compare your comments"
H_PRACTICE = "Practice examples"

# 英語 → クメール語。開発側で仮に訳した（→ v2-todo.md A-9）
KM = {
    H_RESEARCH: "សំណួរស្រាវជ្រាវសម្រាប់ខែនេះ",
    H_AI_SUMMARY: "សេចក្តីសង្ខេបនៃការសិក្សារបស់អ្នកដោយ AI",
    H_DAILY: "ការឆ្លុះបញ្ចាំងប្រចាំថ្ងៃ",
    H_FOCUS: "ចំណុចផ្តោតរបស់អ្នកបានផ្លាស់ប្តូរយ៉ាងណា",
    H_TIMELINE: "កាលប្បវត្តិនៃការឆ្លុះបញ្ចាំង",
    H_LESSON_STUDY: "កំណត់ត្រាការសិក្សាបទបង្រៀន",
    H_SESSIONS: "វេនសិក្សា",
    H_COMPARE: "ប្រៀបធៀបមតិយោបល់របស់អ្នក",
    H_PRACTICE: "ឧទាហរណ៍នៃការអនុវត្ត",
}

SEP = "  ·  "

# バッチが書き換えるセクション。見出し → そのあと何を探すか
MANAGED = {
    H_RESEARCH: "heading_2",   # 問いのテキストそのもの
    H_AI_SUMMARY: "callout",   # サマリー本文（英語・クメール語の2つ）
    H_DAILY: "paragraph",      # キーワードの行
    H_FOCUS: "callout",        # Then/Now と 分析（3つ）
}

# バッチが埋めるまでの仮置き。空白のままにしない
PLACEHOLDER_EN = "Being prepared."
PLACEHOLDER_KM = "កំពុងរៀបចំ។"


def label(english: str) -> str:
    """画面に出す見出し。英語とクメール語を1行に並べる。"""
    km = KM.get(english, "")
    return f"{english}{SEP}{km}" if km else english


def placeholder() -> str:
    return f"{PLACEHOLDER_EN}\n{PLACEHOLDER_KM}"


def heading_text(block: Dict[str, Any]) -> str:
    """見出しブロックの文字列。見出しでなければ空。"""
    kind = block.get("type", "")
    if not kind.startswith("heading_"):
        return ""
    items = block.get(kind, {}).get("rich_text", [])
    return "".join(i.get("plain_text", "") for i in items).strip()


def _is(block: Dict[str, Any], english: str) -> bool:
    """この見出しかどうか。

    英語部分の先頭一致で見る。クメール語の訳を差し替えても
    既存ページの目印が壊れないようにするため。
    """
    text = heading_text(block)
    return bool(text) and text.startswith(english)


def find_after(
    blocks: List[Dict[str, Any]], english: str, block_type: str
) -> Optional[str]:
    """見出しを探し、その後ろにある最初の block_type の id を返す。

    **heading_1 がセクションの区切り。** 次の heading_1 に当たったら打ち切る。
    セクションをまたいで別のブロックを掴まないようにするため。

    heading_2 以下はセクションの中身として扱う。RQのテキストは
    heading_2 なので、これで見つけられる。
    """
    seen = False
    for block in blocks:
        kind = block.get("type", "")

        if kind == "heading_1":
            if seen:
                return None          # 次のセクションに来た
            seen = _is(block, english)
            continue

        if not seen:
            # 小見出しもここを通る。セクションに入る前は読み飛ばす
            if heading_text(block) and _is(block, english):
                seen = True
            continue

        if kind == block_type:
            return block["id"]

    return None

def find_all_after(
    blocks: List[Dict[str, Any]], english: str, block_type: str
) -> List[str]:
    """find_after の複数版。見出しの後ろにある block_type の id を全部返す。

    AIサマリーは英語とクメール語で Callout が2つ並ぶので、
    1つ目と2つ目を別々に書き換える必要がある。
    """
    seen = False
    found: List[str] = []
    for block in blocks:
        kind = block.get("type", "")

        if kind == "heading_1":
            if seen:
                return found
            seen = _is(block, english)
            continue

        if not seen:
            if heading_text(block) and _is(block, english):
                seen = True
            continue

        if kind == block_type:
            found.append(block["id"])

    return found



def find_heading(blocks: List[Dict[str, Any]], english: str) -> Optional[str]:
    """見出しそのものの id。"""
    for block in blocks:
        if _is(block, english):
            return block["id"]
    return None


def page_id_from_url(url: str) -> str:
    """NotionのURLから page id を取り出す。

    User.Mypage は URL で持っている（Notionに「任意のページへの
    リレーション」型が無いため）。URL末尾の32桁16進がIDになる。
    """
    if not url:
        return ""
    tail = url.rstrip("/").rsplit("/", 1)[-1].rsplit("-", 1)[-1]
    tail = tail.split("?")[0]
    if len(tail) != 32:
        return ""
    return f"{tail[0:8]}-{tail[8:12]}-{tail[12:16]}-{tail[16:20]}-{tail[20:32]}"
