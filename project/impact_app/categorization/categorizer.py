import os, json, hashlib, logging
from typing import Dict, Any, List, Tuple
from pathlib import Path

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain.schema import Document

log = logging.getLogger('impactdb')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.getenv("CATEGORY_SEED_FILE", "seed_categories.json")
# ====Settings====
EMBED_MODEL=os.getenv("OPENAI_EMBED_MODEL")
LLM_MODEL=os.getenv("OPENAI_LLM_MODEL")
CHROMA_DIR=os.getenv("CHROMA_DIR")
SEED_PATH = os.path.join(BASE_DIR, SEED_FILE)
CATEGORY_MODE=os.getenv("CATEGORY_MODE")

# ===Categorize teachers' comment into 6 types===
CATEGORIES = [
    "0:Teacher/Methods",
    "1:Mass Students",
    "2a:Individual Character",
    "2b:Individual Evaluation",
    "2c:Individual Verification",
    "2d:Learning of how Student Learn",
    "fact:Mentioning facts"
]

emb = OpenAIEmbeddings(model=EMBED_MODEL)
llm = ChatOpenAI(model=LLM_MODEL,temperature=0.8)

HASH_FILE = os.path.join(CHROMA_DIR, ".seed_hash") if CHROMA_DIR else ".seed_hash"

def _seed_hash() -> str:
    """seed_categories.json の MD5 ハッシュを返す"""
    with open(SEED_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def _load_seeds() -> List[Document]:
    """シードJSONを読み込み、空文字を除外してDocumentリストを返す"""
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seeds = json.load(f)
    docs: List[Document] = []
    for cat, examples in seeds.items():
        for i, text in enumerate(examples):
            if not text.strip():
                continue
            docs.append(Document(
                page_content=text,
                metadata={"category": cat, "example_id": f"{cat}-{i}"}))
    return docs

def build_or_load_store() -> Chroma:
    Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)
    store = Chroma(collection_name="categories", embedding_function=emb, persist_directory=CHROMA_DIR)

    current_hash = _seed_hash()

    # ハッシュファイルが存在し、一致すれば再構築不要
    hash_path = Path(HASH_FILE)
    if hash_path.exists():
        stored_hash = hash_path.read_text().strip()
        if stored_hash == current_hash:
            try:
                if store._collection.count() > 0:
                    log.info(f"ChromaDB loaded: {store._collection.count()} docs (seed unchanged)")
                    return store
            except Exception:
                pass

    # シード変更 or 初回: コレクション再構築
    log.info("Seed changed or first run: rebuilding ChromaDB collection")
    try:
        store.delete_collection()
        store = Chroma(collection_name="categories", embedding_function=emb, persist_directory=CHROMA_DIR)
    except Exception:
        pass

    docs = _load_seeds()
    store.add_documents(docs)
    hash_path.write_text(current_hash)
    log.info(f"ChromaDB rebuilt: {len(docs)} docs ingested (hash={current_hash[:8]}...)")
    return store

_store = build_or_load_store()


def _embed_vote(text_en:str, k: int= 5) -> Tuple[str, float, List[Dict[str, Any]]]:
    # """埋め込み近傍多数決。。平均類似度を信頼度に採用"""
    if not text_en.strip():
        return "There is no text", 0.0, []
    results = _store.similarity_search_with_relevance_scores(text_en, k=k)
    counts: Dict[str,List[float]] = {c: [] for c in CATEGORIES}
    evidence: List[Dict[str, Any]] =[]
    for doc, score in results:
        cat = doc.metadata.get("category", "0:Teacher/Methods")
        counts[cat].append(float(score))
        evidence.append({"category": cat, "score": float(score), "example":doc.page_content[:300]})
    best = max(CATEGORIES, key=lambda c:(len(counts[c]), sum(counts[c])/len(counts[c]) if counts[c] else 0.0))
    conf = (sum(counts[best])/len(counts[best])) if counts[best] else 0.0
    conf = max(0.0, min(1.0, conf))
    return best, conf, evidence

def _llm_refine(text_en:str, evidence: List[Dict[str, Any]]) -> Tuple[str, float, str]:
    # 近傍例を提示してLLMに最終判定させる
    ev = "\n".join([f"[{i+1}] ({e['category']}, score={e['score']:.2f}) {e['example']}" for i ,e in enumerate(evidence)])
    sys =("You are a strict JSON-only classifier for teacher comments."
         "Categories: "+", ".join(CATEGORIES) +"."
         "Return JSON: {\"category\":\"...\",\"confidence\":0~1,\"rationale\":\"...\"}.")
    usr = f"Nearest examples:\n{ev}\n\nClassify the input into ONE category:\n---\n{text_en}\n---"
    resp = llm.invoke([{"role":"system", "content": sys}, {"role":"user", "content":usr}])

    try:
        data=json.loads(resp.content)
        cat = data.get("category", "")
        conf = float(data.get("confidence", 0.0))
        rat = data.get("rationale","")
        if cat not in CATEGORIES:
            cat = evidence[0]["category"] if evidence else "None Evidence"
        return cat, conf, rat
    except Exception:
        return (evidence[0]["category"] if evidence else "Error None Evidence")

def categorize(text_en:str) -> Dict[str,Any]:
    """公開API：テキスト→{category, confidence, evidence, rationale}"""
    base_cat, conf_embed, ev=_embed_vote(text_en,k=5)
    if CATEGORY_MODE == "embed":
        return {"category": base_cat, "confidence":conf_embed, "evidence":ev,"rationale": "embed_only"}
    # hybrid
    cat, conf_llm, rat= _llm_refine(text_en,ev[:3])
    final_cat = cat or base_cat
    final_conf = max(conf_embed, conf_llm) if conf_llm else conf_embed
    return {"category": final_cat, "confidence": float(final_conf), "evidence":ev[:3], "rationale": rat}




# === *No USE!! Basic structure of Using Open AI ===
# CATEGORIES = ["praise", "specific_advice", "open_question", "directive", "observation"]

# def classify(en_text:str)-> Tuple[Dict[str,Any], bool]:
#     # GPTへの司令
#     sys = (
#         'Classify teacher feedback into categories:'
#         +','.join(CATEGORIES)
#         +'. Respond JSON: {\'labels\':[], \'confidence\':0-1, \'rationale\':\'...\'}'
#     )
#     r = oai.chat.completions.create(
#         model='gpt-4o-mini',
#         messages=[
#             {'role': 'system', 'content': sys},
#             {'role':'user', 'content': f'Text:\n{en_text}\nOutput JSON only.'}
#         ],
#         temperature=0.2
#     )
#     raw=r.choices[0].message.content.strip()
#     try:
#         data = json.loads(raw)
#     except Exception:
#         data = {'labels': [], 'confidence':0.5, 'rationale': raw}
#     need_review = (data.get('confidence', 0) < 0.7) or (not data.get('label'))
#     return data, need_review