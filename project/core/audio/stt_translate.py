from core.audio.audio_preprocess import preprocess_for_stt
from core.audio.stt_chunking import ms_to_ts, split_wav_to_chunks
from openai import OpenAI
import os,logging


OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
oai = OpenAI(api_key = OPEN_API_KEY)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

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