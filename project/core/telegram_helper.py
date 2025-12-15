
# ===== Telegram Helpers =====
import logging
from typing import Any, Dict, Tuple
import requests
import ulid
class TelegramFileDownloadError(Exception):
    pass

from core.config import NARRATIVE_TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

def tg_api(method:str, token:str, **params)-> Dict[str,Any]:
    url = f'https://api.telegram.org/bot{token}/{method}'
    r=requests.post(url,data=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get('ok'):
        raise RuntimeError(f'TelegramAPI error: {data}')
    return data

def tg_get_file_url(file_id: str, token:str)->str:
    r = requests.get(
        f'https://api.telegram.org/bot{token}/getFile',
        params={'file_id': file_id},
        timeout=30
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise TelegramFileDownloadError(f"getFile failed {data}")
    file_path=r.json()['result']['file_path']
    return f"https://api.telegram.org/file/bot{token}/{file_path}"

def tg_send_message(chat_id:int, token:str,text:str):
    try:
        tg_api('sendMessage',token, chat_id=chat_id,text=text)
    except Exception as e :
        log.warning(f'sendMessage failed: {e}')

def new_id() -> str:
    return str(ulid.new())

# def get_file_url(file_id: str, token:str) -> str:
#     # get the furl which can access to the media data based on the telegram url
#     file_path = tg_get_file_url(file_id, token)
#     file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
#     return file_url