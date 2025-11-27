import os, json, tempfile, logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional,List, Tuple
from core.notion_client import get_notion_client

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from core.audio.audio_preprocess import preprocess_for_stt
from core.audio.helpers_audio import pick_audio_from_message
from core.audio.stt_chunking import ms_to_ts, split_wav_to_chunks
from impact_app.notion.notion_client import ensure_training_space
from impact_app.categorization.categorizer import categorize
from narrative_app.service import handle_telegram_update; load_dotenv()
import requests
import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI
import ulid 

# ===== Settings =====
OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
IMPACT_TELEGRAM_BOT_TOKEN = os.getenv('IMPACT_TELEGRAM_BOT_TOKEN')
IMPACT_TELEGRAM_SECRET_TOKEN= os.getenv('IMPACT_TELEGRAM_SECRET_TOKEN')
NARRATIVE_TELEGRAM_BOT_TOKEN=os.getenv('NARRATIVE_TELEGRAM_BOT_TOKEN')
NARRATIVE_TELEGRAM_SECRET_TOKEN=os.getenv('NARRATIVE_TELEGRAM_SECRET_TOKEN')
PUBLIC_BASE_URL= os.getenv('PUBLIC_BASE_URL')

# NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
# ENABLE_TRANSLATION = os.getenv("ENABLE_TRANSLATION", "false").lower() == "true"


if not all([IMPACT_TELEGRAM_BOT_TOKEN, IMPACT_TELEGRAM_SECRET_TOKEN]):
    raise RuntimeError('Missing required env vars. Check .env')

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

# Open Ai client
oai = OpenAI(api_key = OPEN_API_KEY)
notion = get_notion_client()

# ===== Helpers =====
def tg_api(method:str, **params)-> Dict[str,Any]:
    url = f'https://api.telegram.org/bot{IMPACT_TELEGRAM_BOT_TOKEN}/{method}'
    r=requests.post(url,data=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get('ok'):
        raise RuntimeError(f'TelegramAPI error: {data}')
    return data

def tg_get_file_url(file_id: str)->str:
    r = requests.get(
        f'https://api.telegram.org/bot{IMPACT_TELEGRAM_BOT_TOKEN}/getFile',
        params={'file_id': file_id},
        timeout=30
    )
    r.raise_for_status()
    file_path=r.json()['result']['file_path']
    return f"https://api.telegram.org/file/bot{IMPACT_TELEGRAM_BOT_TOKEN}/{file_path}"

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

        r= oai.chat.completions.create(model='gpt-4o-mini',messages=msgs)
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
def impact_process_update(update:Dict[str, Any]):
    msg = update.get('message') or {}
    chat = msg.get('chat') or {}
    chat_id = chat.get('id')
    chat_type = chat.get('type')
    training_name = chat.get('title') or "Unknown Training"
    message_id = msg.get('message_id')

    # ---extract music---
    audio_info = pick_audio_from_message(msg)
    if not audio_info:
        if chat_id:
            tg_send_message(chat_id, "Please send Music file(MP3)")
        return
    
    #---Making sureTraining pages & DB inside of the page exist in Notion---
    try:
        training_page_id, training_db_id =  ensure_training_space(chat_id, training_name)
    except Exception as e:
        log.exception(f"ensure_training_space failed: {e}")
        if chat_id:
            tg_send_message(chat_id, "There is no connection to Notion page & Notion DB")
        return
    
    #--- Music File DL---
    file_id = audio_info["file_id"]
    duration = audio_info.get("duration")
    file_url = tg_get_file_url(file_id)

    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, (audio_info.get("file_name") or "in.bin"))
        with requests.get(file_url, stream=True, timeout=180) as r:
            r.raise_for_status()
            with open(src,'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        
        #--- SST(chunking & Preprocess) using transcribe---
        stt_text_km, stt_conf = transcribe(src)
    
    # ---Translate---
    trans_en_text, trans_src = translate_km_to_en(stt_text_km)
    base_for_classify = trans_en_text or stt_text_km

    #--- Classification using Open AI Embedding/ OpenAI---
    cat_res = categorize(base_for_classify)
    category = cat_res["category"]
    category_conf = float(cat_res["confidence"])
    evidence = cat_res.get("evidence", [])
    rationale = cat_res.get("rationale", "")

    #--- Store data in Notion---
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    # "Name" property in the DB is file name of the uploaded file. If no, date+chat_id
    base_file_name = (audio_info.get("file_name") or "").strip()
    if base_file_name:
        name_no_ext = os.path.splitext(base_file_name)[0]
    else:
        name_no_ext = f"{now_iso[:10]}_{chat_id or ''}"
    
    def rt_prop(text:str, chunk:int=1900):
        s = (text or "")
        parts = [s[i:i+chunk] for i in range(0, len(s), chunk)] or [""]
        return {"rich_text": [{"type":"text", "text":{"content":p}} for p in parts]}
    
    props = {
        "Name": {'title': [{'type':'text', 'text':{'content': name_no_ext}}]},
        "Date": {'date': {'start':now_iso}},
        "STT_Km": rt_prop(stt_text_km),
        "Translated_En": rt_prop(trans_en_text),
        "Category": {"select":{"name": category}},
        "CategoryConfidence": {"number": category_conf},
        "AudioURL":{'url': file_url},
        "ChatID": {'number': chat_id if chat_id is not None else 0},
        "MessageID": {'number': message_id if message_id is not None else 0},
        "ExternalID": {'rich_text': [{'type':'text', 'text': {'content': f"tg:{update.get('update_id')}"}}]},
    }
    
    # Add Evidence to the child of each page
    extra_children = []
    if evidence:
        extra_children.append({
            "object": "block", "type": "heading_2",
            "heading_2":{"rich_text":[{"type":"text", "text":{"content": "Category Evidence"}}]}
        })
        for i , ev in enumerate(evidence, start=1):
            txt = f"[{i}]({ev['category']}, score={ev['score']:.2f}) {ev['example']}"
            extra_children.append({
                "object": "block", "type":"paragraph",
                "paragraph":{"rich_text": [{"type":"text", "text":{"content":txt}}]}
            })
    
    if rationale:
        extra_children.append({
            "object":"block", "type":"paragraph",
            "paragraph": {"rich_text":[{"type":"text", "text":{"content":f'Rationale:{rationale}'}}]}
        })
    
    # Save the date to child DB of each Training
    page_id = create_or_update_notion_page(
        training_db_id,props, stt_text_km, trans_en_text, extra_children
    )
    
    if chat_id:
        tg_send_message(
            chat_id,
            f"Saved data to {training_name} \n"
            f"File Name: {name_no_ext} \n"
            f"Duration={duration or '-'} sec / Start from: {stt_text_km[:50]}..."
        )
    

# Fast API
app = FastAPI()

@app.get('/healthz')
def healthz():
    return {'ok': True, 'time': datetime.now(timezone.utc).isoformat()}

@app.post('/telegram/impact/webhook')
async def impact_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != IMPACT_TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail='Invalid secret token')
    update = await request.json()
    # すぐACK、重い処理は裏で
    background.add_task(impact_process_update, update)
    return JSONResponse({'ok': True})

@app.post('/telegram/narrative/webhook')
async def narrative_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != NARRATIVE_TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid secret Token for narrative bot")
    update = await request.json()
    background.add_task(handle_telegram_update,update)
    return JSONResponse({"ok": True})