import os, json, tempfile, logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional,List, Tuple
from notion_client import Client as Notion

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from helpers_audio import pick_audio_from_message
from audio.audio_preprocess import preprocess_for_stt
from audio.stt_chunking import split_wav_to_chunks, ms_to_ts; load_dotenv()
import requests
import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI
import ulid 
from categorization.categorizer import categorize

# ===== Settings =====
OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_SECRET_TOKEN= os.getenv('TELEGRAM_SECRET_TOKEN')
PUBLIC_BASE_URL= os.getenv('PUBLIC_BASE_URL')

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
# ENABLE_TRANSLATION = os.getenv("ENABLE_TRANSLATION", "false").lower() == "true"


if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_SECRET_TOKEN, NOTION_API_KEY , NOTION_DATABASE_ID]):
    raise RuntimeError('Missing required env vars. Check .env')

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

# Open Ai client
oai = OpenAI(api_key = OPEN_API_KEY)
notion = Notion(auth=NOTION_API_KEY)

# ===== Helpers =====
def tg_api(method:str, **params)-> Dict[str,Any]:
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}'
    r=requests.post(url,data=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get('ok'):
        raise RuntimeError(f'TelegramAPI error: {data}')
    return data

def tg_get_file_url(file_id: str)->str:
    r = requests.get(
        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile',
        params={'file_id': file_id},
        timeout=30
    )
    r.raise_for_status()
    file_path=r.json()['result']['file_path']
    return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

def tg_send_message(chat_id: int, text:str):
    try:
        tg_api('sendMessage', chat_id=chat_id,text=text)
    except Exception as e :
        log.warning(f'sendMessage failed: {e}')

def new_id() -> str:
    return str(ulid.new())



def transcribe(file_path: str) -> tuple[str,float]:
    # 1 前処理（VADはまず無効で全文残す）
    # 2 30s + 1.5s overlapでチャンク化
    # 3 チャンクごとにWhisperへ
    # 4 連結（タイムスタンプもつける）

    # 1前処理
    wav = preprocess_for_stt(file_path)
    # 2チャンク化
    chunks = split_wav_to_chunks(wav, chunk_ms=30_000, overlap_ms=1_5000)
    # 3 チャンクごとにWhisperへ
    texts = []
    for idx, (cpath, s_ms, e_ms) in  enumerate(chunks, start=1):
        with open(cpath, 'rb') as f :
          tr = oai.audio.transcriptions.create(
              model="gpt-4o-transcribe",
              file=f,
              prompt="The audio is in Khmer(km). Write Khmer scripts accurately."
          )
        chunk_text = getattr(tr, "text", "") or ""
        # 区切りをつけて連結
        texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {chunk_text}")
    
    full_text = "\n".join(texts).strip()
    return full_text, 0.9




def translate_km_to_en(text:str) -> tuple[str,str]:
    # 1st: Google Trasnlate
    try:
        from google.cloud import translate_v2 as translate
        client = translate.Client()
        res = client.translate(text, target_language='en', source_language='km')
        return res['translatedText'], 'google'
    except Exception as e:
        log.warning(f"GCP translate failed, fallback OpenAI: {e}")
        # 2nd: OpenAI
        msgs = [
            {'role': 'system', 'content': 'you translate khmer to clear Eng'},
            {'role': 'user', 'content': text}
        ]

        r= oai.chat.completions.create(model='chatgpt-4o-mini',messages=msgs)
        en = r.choices[0].message.content.strip()
        return en, 'openai'

CATEGORIES = ["praise", "specific_advice", "open_question", "directive", "observation"]

def classify(en_text:str)-> Tuple[Dict[str,Any], bool]:
    # GPTへの司令
    sys = (
        'Classify teacher feedback into categories:'
        +','.join(CATEGORIES)
        +'. Respond JSON: {\'labels\':[], \'confidence\':0-1, \'rationale\':\'...\'}'
    )
    r = oai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'system', 'content': sys},
            {'role':'user', 'content': f'Text:\n{en_text}\nOutput JSON only.'}
        ],
        temperature=0.2
    )
    raw=r.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
    except Exception:
        data = {'labels': [], 'confidence':0.5, 'rationale': raw}
    need_review = (data.get('confidence', 0) < 0.7) or (not data.get('label'))
    return data, need_review

# Notion Helper
def chunk(text:str, size:int=1000) -> List[str]:
    return [text[i:i+size] for i in range(0, len(text), size)] or [""]


def page_exists_by_external_id(database_id: str, external_id:str) -> Optional[str]:
    # external_id(rich_text)が一致するページがあればそのIDを返す
    try:
        res = notion.databases.query(
            **{
                'database_id': database_id,
                'filter': {'property':'ExternalID', 'rich_text':{'equals':external_id}},
                'page_size': 1
            }
        )
        results = res.get('results', [])
        return results[0]['id'] if results else None
    except Exception as e:
        log.warning(f"Notion query failed: {e}")
        return None

def create_or_update_notion_page(
        db_id: str, properties:Dict[str,Any], transcript_km: str, transcript_en:str, extra_children:Optional[List[Dict[str,Any]]] =None
)-> str:
    # 先にExternalIDがあれば更新、なければ作成
    external_id = ''.join([
        t['text']['content']
        for t in properties['ExternalID']['rich_text']
    ]) if 'ExternalID' in properties else None

    page_id = page_exists_by_external_id(db_id, external_id) if external_id else None

    children = []
    if transcript_km:
        children.append({
            'object': 'block', 'type': 'heading_2',
            'heading_2': {'rich_text': [{'type':'text','text':{'content': 'Transcript (KM)'}}]}
        })
    
    if transcript_en:
        children.append({
            "object":"block","type":"heading_2",
            "heading_2":{"rich_text":[{"type":"text","text":{"content":"Translation (EN)"}}]}
        })
        for part in chunk(transcript_en):
            children.append({
                "object":"block","type":"paragraph",
                "paragraph":{"rich_text":[{"type":"text","text":{"content":part}}]}
            })
    # Evidenceなどを後ろに連結
    if extra_children:
        children.extend(extra_children)
    
    if page_id:
         notion.pages.update(page_id=page_id, properties=properties)
         return page_id
    else:
        res = notion.pages.create(
            parent={'database_id': db_id},
            properties=properties,
            children=children
        )
        return res['id']


# Processing
def process_update(update:Dict[str, Any]):
    msg = update.get('message') or {}
    chat = msg.get('chat') or {}
    chat_id = chat.get('id')
    message_id = msg.get('message_id')

    # ーーーーーTelegramへの音声ファイルを取得ーーーー
    # ← ここが変更点：音声抽出を関数化して mp3(document/audio) を優先
    audio_info = pick_audio_from_message(msg)
    if not audio_info:
        if chat_id:
            tg_send_message(chat_id, "Send Music file like mp3")
            return
    
    file_id = audio_info["file_id"]
    duration = audio_info.get("duration")
    file_url = tg_get_file_url(file_id)

    # ダウンロード → 16kHz mono WAV 正規化 → STT（languageは渡さない）
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, (audio_info.get("file_name") or "in.bin"))
        with requests.get(file_url, stream =True, timeout=180) as r:
            r.raise_for_status()
            with open(src,'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            stt_text_km, stt_conf = transcribe(src)

    # そのままtranscribe(src)を呼ぶ（この内部で前処理＆分割&連結）
    
    trans_en_text, trans_src = translate_km_to_en(stt_text_km)
    base_for_classify = trans_en_text or stt_text_km

    # ====Category Classification ===
    cat_res = categorize(base_for_classify)
    category = cat_res["category"]
    category_conf = float(cat_res["confidence"])
    evidence = cat_res.get("evidence", [])
    rationale = cat_res.get("rationale","")
     # ====Category Classification ===


    # Notion保存処理
    clf, need_review = classify(base_for_classify)

    now_iso = datetime.now(timezone.utc).isoformat()
    name = f"{now_iso[:10]} {chat_id or ''}"
    labels = [{'name': lab} for lab in clf.get('labels', []) if lab in CATEGORIES]

    def rt_prop(text:str, chunk:int=1900):
        # Notion rich_textプロパティように、文字列を配列か、長文は分割。
        s = (text or "")
        parts = [s[i:i+chunk] for i in range(0,len(s), chunk)] or [""]
        return {"rich_text": [{"type":"text", "text":{"content":p}} for p in parts]}
    
    props = {
        "Name": {'title': [{'type':'text','text':{'content':name}}]},
        "Date": {'date':{'start':now_iso}},
        "Tags": {'multi_select': labels},
        "STT_Km": rt_prop(stt_text_km),
        "Translated_En":rt_prop(trans_en_text),
        "Confidence": {'number': float(clf.get('confidence',0))},
        "NeedReview": {'checkbox': bool(need_review)},
        "AudioURL": {'url': file_url},
        "ChatID": {'number': message_id if message_id is not None else 0},
        "ExternalID": {'rich_text': [{'type':'text', 'text':{'content': f"tg:{update.get('update_id')}"}}]},
    }

     # ====Props Update Category Classification ===
    props.update({
        "Category": {"select": {"name": category}},
        "CategoryConfidence": {"number": category_conf}         
    })
     # ====Props Update Category Classification ===

     # 本文に「Category Evidence」を追記したい場合は children にブロックを追加
    extra_children = []
    if evidence:
        extra_children.append({
            "object":"block", "type": "heading_2",
            "heading_2":{"rich_text": [{"type": "text", "text":{"content": "Category Evidence"}}]}
        })
        for i, ev in enumerate(evidence, start=1):
            txt = f"[{i}] ({ev['category']}, score={ev['score']:2f}) {ev['example']}"
            extra_children.append({
                "object": "block", "type":"paragraph",
                "paragraph": {"rich_text": [{"type":"text", "text": {"content":txt}}]}
            })
        if rationale:
            extra_children.append({
                "object": "block", "type":"paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": f'Rationale:{rationale}'}}]}

            })

    page_id = create_or_update_notion_page(
        NOTION_DATABASE_ID, props, stt_text_km, trans_en_text, extra_children
    )

    if chat_id:
        tg_send_message(
            chat_id,
            f"STT finished Successfully ({audio_info['source']}) \n"
            f"length={duration or '-'} sec / preview: {stt_text_km[:60]}..."
        )
    
    




# Fast API
app = FastAPI()

@app.get('/healthz')
def healthz():
    return {'ok': True, 'time': datetime.now(timezone.utc).isoformat()}

@app.post('/telegram/webhook')
async def telegram_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail='Invalid secret token')
    update = await request.json()
    # すぐACK、重い処理は裏で
    background.add_task(process_update, update)
    return JSONResponse({'ok': True})