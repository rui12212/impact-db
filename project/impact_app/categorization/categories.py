"""教員コメントの分類カテゴリー定義（単一の正）。

カテゴリー名（name）が識別子。level と color は付け替え可能な属性として持つ。
level を変えてもコード・seed_categories.json の修正は不要。

依存を持たない軽量モジュールにしている（categorizer.py はインポート時に
ChromaDB を構築するため、定義を参照したいだけの箇所から読めるように分離）。

2026-10-02 更新:
  - 先方の団体から定義をもらい、8分類に改めた（2c+ を追加）
  - level に数値を割り当てるのをやめ、Notion の Select の色で段階を表す
  - 色は「指導法 → 集団 → 個の様子 → 理解 → 要因 → 問い → 実践」の順に並べた
    Notion の色は10色固定で緑の濃淡が作れないため、グラデーションではなく
    順序のある配色にしている（凡例で段階を補う必要がある）

  ⚠️ example / seed_categories.json の例文は旧定義のまま引き継いでいる。
     特に level 0 / 2a / 2d は定義の意味が変わったため、例文の見直しが必要。
     2c+ には例文が無く、追加されるまで AI はこの分類を選べない。
"""
from typing import Any, Dict, List

# color は Notion の Select オプション用
#   (default/gray/brown/orange/yellow/green/blue/purple/pink/red)
CATEGORY_SPECS: List[Dict[str, str]] = [
    {
        "name": "Teaching Methods",
        "level": "0",
        "color": "gray",
        "definition": "Looks at how the lesson was taught, rather than at the students.",
        "definition_ja": "指導法の視点",
        "example": "When the teacher asked the students to make English sentences, he made sure that it should not make the same one. By doing so, the four students were able to create four different things. I thought it was very effective."
    },
    {
        "name": "Whole Class",
        "level": "1",
        "color": "brown",
        "definition": "Speaks about the students as a group, not as individuals.",
        "definition_ja": "集団の視点",
        "example": "The students in this class enjoyed the discussion. I realized that the students want to learn and become proactive when they link the topic with their own future."
    },
    {
        "name": "Individual Behaviour",
        "level": "2a",
        "color": "orange",
        "definition": "Notices what a particular student did, or how they appeared.",
        "definition_ja": "様子への着目",
        "example": "Student A could not concentrate on if the topic went to about difficult math. I wonder how I can attract him."
    },
    {
        "name": "Individual Understanding",
        "level": "2b",
        "color": "yellow",
        "definition": "Notices how well a particular student understood.",
        "definition_ja": "理解度への着目",
        "example": "I was very impressed with the student B presentation. It was very good as it was beyond my expectations."
    },
    {
        "name": "Examining Causes",
        "level": "2c",
        "color": "green",
        "definition": "Examines why the student behaved or understood that way.",
        "definition_ja": "要因の検証",
        "example": "Student C started writing something in his notebook but when the teacher asked to take notes he stopped writing it."
    },
    {
        "name": "Questioning Practice",
        "level": "2c+",
        "color": "blue",
        "definition": "Turns the observation into a question about one's own teaching.",
        "definition_ja": "実践への問い",
        "example": ""
    },
    {
        "name": "Connecting to Practice",
        "level": "2d",
        "color": "purple",
        "definition": "Draws from the observation something to change in one's own teaching.",
        "definition_ja": "実践への接続",
        "example": "Student D writes down the numbers that student E tells him. He wrote down the numbers that he gave him but he didn't know what the numbers meant. He had the numbers in his hand but he didn't know how to graph them. I realized I always checked the worksheets and notebooks to see how far that child has progressed, however this does not mean that he or she understands the subject matter."
    },
    {
        "name": "Pure Observation",
        "level": "fact",
        "color": "default",
        "definition": "States only what was observed, with no interpretation or evaluation.",
        "definition_ja": "解釈・評価が一切含まれない",
        "example": "I realised the students took note about the triangles and squares. Other students also watched it and tried to copy it on his textbook."
    },
]

# 以下は CATEGORY_SPECS から導出する。直接編集しないこと。
CATEGORIES: List[str] = [s["name"] for s in CATEGORY_SPECS]

CATEGORY_DEFINITIONS: Dict[str, Dict[str, str]] = {
    s["name"]: {"definition": s["definition"], "example": s["example"]}
    for s in CATEGORY_SPECS
}

CATEGORY_LEVELS: Dict[str, str] = {s["name"]: s["level"] for s in CATEGORY_SPECS}
CATEGORY_COLORS: Dict[str, str] = {s["name"]: s["color"] for s in CATEGORY_SPECS}


def category_label(name: str) -> str:
    """表示・保存用のラベルを組み立てる（例: "0:Teacher/Methods"）。

    level は変わりうるため、合成済みの文字列は持ち回さず必要な箇所で都度組み立てる。
    """
    level = CATEGORY_LEVELS.get(name)
    return f"{level}:{name}" if level else name


def category_select_options() -> List[Dict[str, Any]]:
    """Notion の Select プロパティに渡す options を組み立てる。"""
    return [
        {"name": category_label(s["name"]), "color": s["color"]}
        for s in CATEGORY_SPECS
    ]
