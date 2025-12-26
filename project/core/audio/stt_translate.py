from core.audio.audio_preprocess import preprocess_for_stt
from core.audio.stt_chunking import ms_to_ts, split_wav_to_chunks
from openai import OpenAI
import os,logging, time
from typing import Optional, Tuple, List
import requests
import mimetypes
from elevenlabs.client import ElevenLabs
from google import genai
from google.genai import types

OPEN_API_KEY = os.getenv('OPENAI_API_KEY')
oai = OpenAI(api_key = OPEN_API_KEY)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('impactdb'
)

def oai_transcribe(file_path: str) -> str:
    # 1 前処理（VADはまず無効で全文残す）
    # 2 30s + 1.5s overlapでチャンク化
    # 3 チャンクごとにWhisperへ
    # 4 連結（タイムスタンプもつける）

    # 1前処理
    wav = preprocess_for_stt(file_path)
    # 2チャンク化
    chunks = split_wav_to_chunks(wav, chunk_ms=30_000, overlap_ms=1_500)
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
    return full_text #0.9


def oai_translate_km_to_en(text:str) -> str:
    # 1st: Google Trasnlate
    try:
        msgs = [
            {'role': 'system', 'content': 'you translate khmer to clear Eng'},
            {'role': 'user', 'content': text}
        ]

        r= oai.chat.completions.create(model='gpt-4o-mini',messages=msgs)
        en = r.choices[0].message.content.strip()
        return en
    except Exception as e:
        log.warning(f"OpenAI Translate failed: {e}")


# common helper (HTTP Polling)
def _poll_json(
        url: str,
        headers: dict,
        *,
        interval_sec: float = 2.5,
        timeout_sec: float = 180.0,
) -> dict:
    start = time.time()
    while True:
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()

        status = (data.get("status") or "").lower()
        if status in ("completed", "done"):
            return data
        if status in ("error", "failed", "cancelled","canceled"):
            raise RuntimeError(f"Polling failed: status={status}, body={data}")
        
        if time.time() - start > timeout_sec:
            raise TimeoutError(f"Polling timeout: {url}")
        
        time.sleep(interval_sec)

# 1) AssemblyAI: Khmer->Eng
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

def transcribe_assemblyai_km_to_en(file_path: str) -> tuple[str, float]:
    
    if not ASSEMBLYAI_API_KEY:
        raise RuntimeError("AssemblyAI_API_KEY is not set")
    
    wav = preprocess_for_stt(file_path)
    chunks = split_wav_to_chunks(wav, chunk_ms=30_000, overlap_ms=1_500)
    headers = {"Authorization": ASSEMBLYAI_API_KEY}

    en_texts: List[str] = []
    km_texts: List[str] = []
    confs: List[float] = []

    for idx, (cpath, s_ms, e_ms) in enumerate(chunks, start=1):
        # 1:upload
        with open(cpath, "rb") as f:
            up = requests.post(
                "https://api.assemblyai.com/v2/upload",
                headers=headers,
                data=f,
                timeout=120,
            )
        up.raise_for_status()
        audio_url = up.json()["upload_url"]

        # 2:transcribe + translate in one request
        body = {
            "audio_url": audio_url,
            "language_code": "km",
            "speech_understanding": {
                "request": {
                    "translation": {
                        "target_languages": ["en"],
                        "formal": False
                    }
                }
            }
        }

        res = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers = {**headers, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        res.raise_for_status()
        tid = res.json()["id"]

        tr = _poll_json(
            f"https://api.assemblyai.com/v2/transcript/{tid}",
            headers=headers,
            timeout_sec=300,
        )

        km = tr.get("text") or ""
        km_texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {km.strip()}")

        en = (tr.get("translated_texts") or {}).get("en") or tr.get("text") or ""
        en_texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {en.strip()}")

        # c = tr.get("confidence")
        # if isinstance(c, (int,float)):
        #     confs.append(float(c))
    km_full_text = "\n".join(km_texts).strip()
    en_full_text = "\n".join(en_texts).strip()
    # avg_conf = sum(confs) / len(confs) if confs else 0.0
    return km_full_text, en_full_text # avg_conf


# 2: Gladia:upload -> pre-recorded(translation=true, target=["en"]) -> poll
GLADIA_API_KEY = os.getenv("GLADIA_API_KEY")

def _guess_mime(path:str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "audio/wav" #default is wav, since the chunk is wav

def _raise_with_body(r: requests.Response, label: str) -> None:
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        body = ""
        try:
            body = r.text
        except Exception:
            body = "<failed to read body>"
        raise RuntimeError(f"{label} failed: {e} / status={r.status_code} / body={body}") from e

def transcribe_gladia_km_to_en(file_path: str) -> tuple[str, float]:
    
    if not GLADIA_API_KEY:
        raise RuntimeError("GLADIA_API_KEY is not set")
    
    wav = preprocess_for_stt(file_path)
    chunks = split_wav_to_chunks(wav, chunk_ms=30_000, overlap_ms=1_500)

    headers = {"x-gladia-key":GLADIA_API_KEY,
               "accept":"application/json",
    }
    
    km_texts: List[str] = []
    en_texts: List[str] = []

    for idx, (cpath, s_ms, e_ms) in enumerate(chunks, start=1):
        # 0: zero byte check
        size = os.path.getsize(cpath)
        if size <= 0:
            raise RuntimeError(f"Chunk file is empty: {cpath}")

        filename = os.path.basename(cpath)
        if not filename.lower().endswith(".wav"):
            filename = filename + ".wav"

        # 1 upload (multipart/form-data)
        with open(cpath, "rb") as f:
            up = requests.post(
                "https://api.gladia.io/v2/upload",
                headers=headers,
                files={"audio": (filename, f, "audio/wav")},
                timeout=120,
            )

        up.raise_for_status()

        # Check the Error from the body
        if up.status_code != 200:
            _raise_with_body(up, "Gladia upload")

        audio_url = up.json()["audio_url"]
        if not audio_url:
            raise RuntimeError(f"Upload response missing audio_url: {up.text}")

        # 2 start pre-recorded job (translation enabled)
        body = {
            "audio_url": audio_url,
            "language_config": {
                "languages": ["km"],
                "code_switching": False
            },
            "translation": True,
            "translation_config": {
                "model": "base",
                "target_languages": ["en"],
                "context_adaptation": False,
                "informal": False,
            },
            "diarization": False,
            "subtitles": False,
        }
        
        job = requests.post(
            "https://api.gladia.io/v2/pre-recorded",
            headers={**headers, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )

        job.raise_for_status()

        # check the job response & Error
        if job.status_code not in (200,201):
            _raise_with_body(job, "Gladia pre-recorded init")

        job_id = job.json()["id"]
        if not job_id:
            raise RuntimeError(f"Pre-recorded init response missing id: {job.text}")

        result_url = f"https://api.gladia.io/v2/pre-recorded/{job_id}"

        # 3 poll result
        data = _poll_json(result_url, headers=headers, timeout_sec=300)

        # Km_sst
        km = ""
        try:
            km = (
              data.get("result", {})
              .get("transcription", {})
              .get("full_transcript", "")
            ) or ""
        except Exception:
            km = ""
    
        # Eng_translation result location (per API reference)
        en = ""
        try:
            en = (
                data.get("result", {})
                .get("translation", {})
                .get("results", [{}])[0]
                .get("full_transcript", "")
            ) or ""
        except Exception:
            en = ""

        km = km.strip()
        en = en.strip()
        
        # fallback: transcription full_transcript
        if not en:
            en = km
        
        km_texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {km}")
        en_texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {en}")
    
    km_full_text = "\n".join(km_texts).strip()
    en_full_text = "\n".join(en_texts).strip()
    return km_full_text, en_full_text, # 0.0

# 3 ElevenLabs Speech Translation SDK: Khmer -> Eng
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
eleven = ElevenLabs(api_key=ELEVENLABS_API_KEY)

def transcribe_elevenlabs_km(file_path: str) -> str:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    
    # 1 preprocess
    wav = preprocess_for_stt(file_path)
    chunks = split_wav_to_chunks(wav, chunk_ms=30_000, overlap_ms=1_500)

    # 2 STT of each chunk
    texts = []
    # probs = []

    for idx, (cpath, s_ms, e_ms) in enumerate(chunks, start=1):
        with open(cpath, "rb") as f:
            tr = eleven.speech_to_text.convert(
                file=f,
                model_id="scribe_v1",
                language_code="khm",
                diarize=False,
                tag_audio_events=False,
            )
        
        chunk_text = getattr(tr, "text", None) or (tr.get("text") if isinstance(tr, dict) else "") or ""
        texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {chunk_text.strip()}")
        
        # lp = getattr(tr, "language_probability", None) or (tr.get("language_probability") if isinstance(tr, dict) else None)
        # if isinstance(lp, (int, float)):
        #     probs.append(float(lp))
    
    km_full_text = "\n".join(texts).strip()
    # avg_prob = sum(probs) / len(probs) if probs else 0.0
    return km_full_text # avg_prob


def transcribe_gemini_km(file_path: str) -> str:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    wav = preprocess_for_stt(file_path)
    chunks = split_wav_to_chunks(wav, chunk_ms=30_000, overlap_ms=1_500)

    texts :List[str] = []
    for idx, (cpath, s_ms, e_ms) in enumerate(chunks, start=1):
        with open(cpath, "rb") as f:
            audio_data=f.read()
            tr = client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=[
                    "Please transcribe the content of this audio verbatim in the language spoken (Khmer). Translation is not required.",
                    # client.files.upload(file=f),
                    {
                        "inline_data": {
                            "data": audio_data,
                            "mime_type": "audio/wav"
                        }
                    }
                ]
            )
        chunk_text = getattr(tr, "text", "")
        texts.append(f"[{ms_to_ts(s_ms)}-{ms_to_ts(e_ms)}] {chunk_text}")
    
    full_text = "\n".join(texts).strip()
    return full_text

def translate_gemini_km_to_en(km_text: str) -> str:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    try:
      client = genai.Client(api_key=GEMINI_API_KEY)
      rs = client.models.generate_content(
          model="gemini-2.5-flash",
          config=types.GenerateContentConfig(
            system_instruction="You are an advanced Cambodian interpreter. Please translate the given text in to accurate English. Return str",
          ),
          contents=[km_text]
          )
      en = rs.text.strip()
      return en
    except Exception as e:
        log.warning(f"Gemini Translate failed: {e}")

def decide_transcribe_model(file_path: str, model_name: str) -> tuple[str, str]:

    try:
      if model_name == "oai":
          stt_km =  oai_transcribe(file_path)
          translated_to_en = oai_translate_km_to_en(stt_km)
          return stt_km, translated_to_en
      
      if model_name == "assemblyai":
         stt_km, translated_en_text = transcribe_assemblyai_km_to_en(file_path)
         return stt_km, translated_en_text

      if model_name == "gladia":
          stt_km, translated_en_text = transcribe_gladia_km_to_en(file_path)
          return stt_km, translated_en_text
    
      if model_name == "elevenlabs":
          stt_km = transcribe_elevenlabs_km(file_path)
          translated_to_en = oai_translate_km_to_en(stt_km)
          return stt_km, translated_to_en
      
      if model_name == "gemini":
          stt_km = transcribe_gemini_km(file_path)
          translated_to_en = translate_gemini_km_to_en(stt_km)
          return stt_km, translated_to_en
          
      return "No Khmer", "No Eng"
    
    except Exception as e:
        raise RuntimeError(f"STT&Translation failed: {e}")