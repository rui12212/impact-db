# Processing
import os, logging
import tempfile
from typing import Any, Dict

import requests

from core.audio.helpers_audio import pick_audio_from_message
from core.audio.stt_translate import transcribe, translate_km_to_en
from impact_app.categorization.categorizer import categorize
from impact_app.notion.notion_client import create_or_update_notion_page, ensure_training_space
from core.telegram_helper import tg_get_file_url, tg_send_message
from core.config import IMPACT_TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

impact_bot_token = IMPACT_TELEGRAM_BOT_TOKEN

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
            tg_send_message(chat_id,impact_bot_token ,"Please send Music file(MP3)")
        return
    
    #---Making sureTraining pages & DB inside of the page exist in Notion---
    try:
        training_page_id, training_db_id =  ensure_training_space(chat_id, training_name)
    except Exception as e:
        log.exception(f"ensure_training_space failed: {e}")
        if chat_id:
            tg_send_message(chat_id, impact_bot_token,"There is no connection to Notion page & Notion DB")
        return
    
    #--- Music File DL---
    file_id = audio_info["file_id"]
    duration = audio_info.get("duration")
    file_url = tg_get_file_url(file_id, impact_bot_token)

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
            impact_bot_token,
            f"Saved data to {training_name} \n"
            f"File Name: {name_no_ext} \n"
            f"Duration={duration or '-'} sec / Start from: {stt_text_km[:50]}..."
        )
    