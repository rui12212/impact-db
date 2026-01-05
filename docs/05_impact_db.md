# Impact DB - Detailed Documentation

## Table of Contents
- [Overview](#overview)
- [Processing Flow](#processing-flow)
- [Audio Preprocessing Pipeline](#audio-preprocessing-pipeline)
- [STT Engine Comparison](#stt-engine-comparison)
- [Categorization Logic](#categorization-logic)
- [Training Space Management](#training-space-management)
- [Code Reference](#code-reference)

---

## Overview

**Impact DB** processes audio comments from teachers during lesson observations. It transcribes Khmer speech, translates to English, categorizes the content, and stores structured data in dedicated Notion databases per training session.

### Key Features
- **Advanced audio preprocessing**: Noise reduction, filtering, EQ, VAD trimming
- **Multi-engine STT support**: OpenAI Whisper, Google Gemini, AssemblyAI, Gladia, ElevenLabs
- **Hybrid categorization**: ChromaDB embedding search + LLM refinement
- **Auto-organized storage**: Dedicated Notion DB per training chat
- **Explainable results**: Category evidence and rationale stored

### Supported Audio Formats
| Type | MIME Types | Extensions |
|------|-----------|------------|
| Audio message | `audio/ogg`, `audio/mpeg` | `.ogg`, `.mp3` |
| Voice message | `audio/ogg` (Telegram voice) | - |
| Document (audio) | `audio/mpeg`, `audio/wav` | `.mp3`, `.wav`, `.m4a` |

---

## Processing Flow

### High-Level Flow

```
1. Telegram Webhook → FastAPI
2. Extract audio file info (file_id, duration, mime_type)
3. Ensure Training Space (page + DB in Notion)
4. Download audio to temp file
5. Preprocessing pipeline:
   ├─ Convert to 16kHz mono WAV
   ├─ Noise reduction
   ├─ Bandpass filter (70Hz HPF, 7kHz LPF)
   ├─ EQ peaking (700Hz +2.5dB, 1500Hz +2.0dB)
   ├─ Peak normalization (-1dBFS)
   ├─ AGC & compression (target RMS -20dB)
   └─ VAD trimming
6. Split into 30-second chunks (1.5s overlap)
7. For each chunk:
   ├─ STT (Khmer)
   └─ Translation (English)
8. Combine chunks by timestamp
9. Categorization:
   ├─ ChromaDB embedding search (top 5)
   └─ LLM refinement (top 3 evidence)
10. Save to Notion DB with evidence
11. Send Telegram notification
12. Return 200 OK
```

### Detailed Step-by-Step

#### Step 1: Message Reception
```python
# project/main.py
@app.post('/telegram/impact/webhook')
async def impact_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != IMPACT_TELEGRAM_SECRET_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    update = await request.json()
    background.add_task(impact_process_update, update)
    return JSONResponse({"ok": True})
```

#### Step 2: Extract Audio Info
```python
# impact_app/service.py:30
audio_info = pick_audio_from_message(msg)
if not audio_info:
    tg_send_message(chat_id, impact_bot_token, "Please send Music file(MP3)")
    return

file_id = audio_info["file_id"]
duration = audio_info.get("duration")
file_name = audio_info.get("file_name")
```

**`pick_audio_from_message()` logic**:
```python
# core/audio/helpers_audio.py
def pick_audio_from_message(msg: dict) -> Optional[dict]:
    # Priority: voice > audio > document (if audio MIME)
    if "voice" in msg:
        return {
            "file_id": msg["voice"]["file_id"],
            "duration": msg["voice"].get("duration"),
            "mime_type": msg["voice"].get("mime_type"),
            "file_name": None
        }

    if "audio" in msg:
        return {
            "file_id": msg["audio"]["file_id"],
            "duration": msg["audio"].get("duration"),
            "mime_type": msg["audio"].get("mime_type"),
            "file_name": msg["audio"].get("file_name")
        }

    if "document" in msg:
        doc = msg["document"]
        mime = (doc.get("mime_type") or "").lower()
        if mime.startswith("audio/"):
            return {
                "file_id": doc["file_id"],
                "duration": None,
                "mime_type": mime,
                "file_name": doc.get("file_name")
            }

    return None
```

#### Step 3: Ensure Training Space
```python
# impact_app/service.py:38
training_page_id, training_db_id = ensure_training_space(chat_id, training_name)
```

**Training Space Structure**:
```
Root Page (NOTION_ROOT_PAGE_ID)
└── {training_name} (e.g., "TVETSCHOOL_JAN2026")
    └── Inline Database
        └── Records (one per audio message)
```

**Registry Management** (`project/.runtime/chat_registry.json`):
```json
{
  "-4891823124": {
    "training_page_id": "2b34423b-0fc4-81c1-b070-c3e7ad5f0f38",
    "training_db_id": "2b34423b-0fc4-81c1-b2de-c375975c3c50",
    "training_name": "TVETSCHOOL_JAN2026"
  }
}
```

#### Step 4: Download Audio
```python
# impact_app/service.py:48
file_url = tg_get_file_url(file_id, impact_bot_token)

with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, (audio_info.get("file_name") or "in.bin"))
    with requests.get(file_url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(src, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

    # Process audio in temp directory
    # ...
```

#### Step 5: Preprocessing & STT
```python
# impact_app/service.py:60
stt_text_km, translated_en_text = decide_transcribe_model(src, "gemini")
```

**STT Engine Selection**:
- "oai" → OpenAI Whisper
- "gemini" → Google Gemini 2.5 Flash
- "assemblyai" → AssemblyAI (with simultaneous translation)
- "gladia" → Gladia
- "elevenlabs" → ElevenLabs Scribe v1

#### Step 6: Categorization
```python
# impact_app/service.py:65
cat_res = categorize(translated_en_text or stt_text_km)
category = cat_res["category"]
evidence = cat_res.get("evidence", [])
rationale = cat_res.get("rationale", "")
```

**Output Example**:
```python
{
  "category": "2a:Individual Character",
  "confidence": 0.87,
  "evidence": [
    {"category": "2a:Individual Character", "score": 0.92, "example": "Sokha is very creative..."},
    {"category": "0:Teacher/Methods", "score": 0.75, "example": "The teacher used..."},
    {"category": "2b:Individual Evaluation", "score": 0.68, "example": "Student scored..."}
  ],
  "rationale": "The comment focuses on a specific student's personality trait (creative), which aligns with Individual Character category."
}
```

#### Step 7: Save to Notion
```python
# impact_app/service.py:87
props = {
    "Name": {'title': [{'type':'text', 'text':{'content': name_no_ext}}]},
    "Date": {'date': {'start': now_iso}},
    "STT_Km": rt_prop(stt_text_km),
    "Translated_En": rt_prop(translated_en_text),
    "Category": {"select": {"name": category}},
    "AudioURL": {'url': file_url},
    "ChatID": {'number': chat_id},
    "MessageID": {'number': message_id},
    "ExternalID": {'rich_text': [{'type':'text', 'text': {'content': f"tg:{update_id}"}}]},
}

page_id = create_or_update_notion_page(
    training_db_id, props, stt_text_km, translated_en_text, extra_children
)
```

**Child Blocks**:
```python
extra_children = [
    {
        "type": "heading_2",
        "heading_2": {"rich_text": [{"text": {"content": "Category Evidence"}}]}
    },
    # Evidence items
    {
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {"content": "[1](2a:Individual Character, score=0.92) Sokha is very creative..."}}]}
    },
    # Rationale
    {
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {"content": "Rationale: The comment focuses on..."}}]}
    }
]
```

#### Step 8: Telegram Notification
```python
# impact_app/service.py:126
tg_send_message(
    chat_id,
    impact_bot_token,
    f"Saved data to {training_name}\n"
    f"File Name: {name_no_ext}\n"
    f"Duration={duration or '-'} sec / Start from: {stt_text_km[:50]}..."
)
```

---

## Audio Preprocessing Pipeline

### Pipeline Stages

**File**: `core/audio/audio_preprocess.py`

```python
def preprocess_for_stt(src_path: str, vad_aggr: int = 2) -> str:
    """
    Comprehensive audio preprocessing pipeline for STT optimization

    Args:
        src_path: Path to input audio file (any format)
        vad_aggr: VAD aggressiveness (0-3, default 2)

    Returns:
        Path to preprocessed 16kHz mono WAV file

    Pipeline:
        1. Convert to 16kHz mono WAV
        2. Noise reduction
        3. Bandpass filter (70Hz HPF, 7kHz LPF)
        4. EQ peaking (vowel-friendly)
        5. Peak normalization (-1dBFS)
        6. AGC & compression
        7. VAD trimming
    """
```

### Stage 1: Format Conversion

```python
# audio_preprocess.py:11
def _to_wav16k_mono(src_path: str) -> str:
    audio = AudioSegment.from_file(src_path)
    audio = audio.set_frame_rate(16000).set_channels(1)
    out = os.path.join(tempdir, "stage0_16k_mono.wav")
    audio.export(out, format="wav")
    return out
```

**Why 16kHz?**
- Most STT models are trained on 16kHz audio
- Reduces file size (vs 44.1kHz or 48kHz)
- Preserves speech intelligibility (human speech: 80Hz-8kHz)

**Why mono?**
- Stereo adds no value for speech
- Halves file size
- Simplifies processing

### Stage 2: Noise Reduction

```python
# audio_preprocess.py:127
y = nr.reduce_noise(y=y, sr=sr, prop_decrease=0.6, stationary=True)
```

**Parameters**:
- `prop_decrease=0.6`: Reduce noise by 60% (aggressive)
- `stationary=True`: Assume constant background noise

**How it works**:
1. Estimate noise profile from first 0.5 seconds
2. Apply spectral subtraction
3. Preserve speech frequencies

**Trade-off**: Aggressive noise reduction may cause "underwater" effect on very clean recordings

### Stage 3: Bandpass Filter

```python
# audio_preprocess.py:136
sos = _butter_sos_band(70.0, 7000.0, sr, order=4)
y = sosfiltfilt(sos, y)
```

**Filter Design**:
- **70Hz Highpass**: Remove low-frequency rumble, HVAC hum, handling noise
- **7kHz Lowpass**: Remove high-frequency hiss, electronic noise
- **4th-order Butterworth**: Smooth rolloff, minimal phase distortion

**Frequency Response**:
```
 Gain (dB)
   |
 0 |________/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\________
   |      /                    \
-20 |____/                      \____
   |
     0   70Hz            7kHz  20kHz
```

### Stage 4: EQ Peaking (Vowel Enhancement)

```python
# audio_preprocess.py:142
y = _eq_peaking(y, sr, f0=700.0, q=1.2, gain_db=2.5)
y = _eq_peaking(y, sr, f0=1500.0, q=1.2, gain_db=2.0)
```

**Why 700Hz and 1500Hz?**
- These are **formant frequencies** (F1 and F2) critical for vowel recognition
- Khmer language relies heavily on vowel distinctions
- Boosting these frequencies improves intelligibility

**Parameters**:
- `q=1.2`: Moderate bandwidth (not too narrow, not too wide)
- `gain_db=2.5/2.0`: Gentle boost (avoid distortion)

**EQ Curve**:
```
Gain
 +3dB  ^       ^
       |\     /|
 0dB --+------+------
       |      |
     700Hz  1500Hz
```

### Stage 5: Peak Normalization

```python
# audio_preprocess.py:148
y = _normalize_peak(y, peak_db=-1.0)
```

**Purpose**: Ensure signal doesn't clip during subsequent processing

**How it works**:
```python
peak = np.max(np.abs(y))
target = 10 ** (-1.0 / 20.0)  # -1dBFS ≈ 0.891
y = y * (target / peak)
```

**Why -1dBFS and not 0dBFS?**
- Leaves 1dB headroom for rounding errors
- Prevents digital clipping

### Stage 6: AGC & Compression

```python
# audio_preprocess.py:94
y = _agc_and_compress(y, target_rms_db=-20.0, threshold_db=-18.0, ratio=3.0)
```

**Two-stage process**:

1. **AGC (Automatic Gain Control)**:
   ```python
   cur_rms = sqrt(mean(y^2))
   target_rms = 10 ^ (-20.0 / 20.0)  # -20dBFS
   y = y * (target_rms / cur_rms)
   ```
   - Brings average loudness to consistent level
   - Handles quiet recordings

2. **Compression**:
   ```python
   threshold = 10 ^ (-18.0 / 20.0)
   for each sample:
       if |sample| > threshold:
           excess = |sample| - threshold
           sample = threshold + excess / 3.0
   ```
   - Reduces dynamic range (loud parts quieter)
   - Makes speech more uniform
   - `ratio=3.0`: 3:1 compression (gentle)

**Visual**:
```
Input  →  AGC  →  Compression  →  Output
Loud   →  Med  →    Medium     →  Medium
Medium →  Med  →    Medium     →  Medium
Quiet  →  Med  →    Medium     →  Medium
```

### Stage 7: VAD (Voice Activity Detection) Trimming

```python
# audio_preprocess.py:58
y = _vad_trim(y, sr, aggressiveness=2)
```

**Purpose**: Remove silence and non-speech segments

**How it works**:
1. Split audio into 20ms frames
2. Convert to 16-bit PCM
3. Use WebRTC VAD to detect speech
4. Concatenate only speech frames

**Aggressiveness levels**:
| Level | Behavior |
|-------|----------|
| 0 | Very permissive (keeps noise) |
| 1 | Moderate |
| 2 | **Default** (good balance) |
| 3 | Very aggressive (may cut speech) |

**Example**:
```
Before VAD: [silence][speech][silence][speech][noise][speech]
After VAD:           [speech]        [speech]       [speech]
```

### Preprocessing Output

**Resulting audio characteristics**:
- **Format**: 16kHz mono WAV, 16-bit PCM
- **Frequency range**: 70Hz - 7kHz
- **Peak level**: -1dBFS
- **RMS level**: -20dBFS
- **Dynamic range**: Compressed 3:1
- **Silence**: Trimmed

**File size reduction**:
- Original (3 min, 44.1kHz stereo MP3): ~5MB
- Preprocessed (2 min, 16kHz mono WAV): ~3MB (after VAD trim)

---

## STT Engine Comparison

### Available Engines

**File**: `core/audio/stt_translate.py`

| Engine | Model | Language | Translation | Chunking | Cost (per min) |
|--------|-------|----------|-------------|----------|----------------|
| **OpenAI Whisper** | `gpt-4o-transcribe` | Khmer | Separate call | 30s chunks | ~$0.006 STT + $0.0001 translation |
| **Google Gemini** | `gemini-2.5-flash` | Khmer | Separate call | 30s chunks | Free (with quota) |
| **AssemblyAI** | Default | Khmer | Simultaneous | Full file | ~$0.00025 |
| **Gladia** | Base | Khmer | Simultaneous | Full file | Variable |
| **ElevenLabs** | `scribe_v1` | Khmer | Not supported | Full file | ~$0.005 |

### 1. OpenAI Whisper

**Function**: `oai_transcribe(file_path: str) -> Tuple[str, float]`

**Implementation**:
```python
from openai import OpenAI
client = OpenAI()

# Preprocess
preprocessed = preprocess_for_stt(file_path)

# Split into 30s chunks with 1.5s overlap
chunks = split_wav_to_chunks(preprocessed, chunk_sec=30, overlap_sec=1.5)

all_segments = []
for chunk_path in chunks:
    with open(chunk_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=f,
            language="km",  # Khmer
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            prompt="The audio is in Khmer(km). Write Khmer scripts accurately."
        )
    all_segments.extend(resp.segments)

# Combine segments, deduplicate overlaps
combined_text = combine_segments_by_time(all_segments)
return combined_text, avg_confidence
```

**Pros**:
- High accuracy for Khmer
- Segment-level timestamps
- Explicit prompt control

**Cons**:
- Requires chunking (30s limit per call)
- Two API calls (STT + translation)

### 2. Google Gemini

**Function**: `transcribe_gemini_km(file_path: str) -> Tuple[str, List[dict]]`

**Implementation**:
```python
import google.generativeai as genai

model = genai.GenerativeModel("gemini-2.5-flash")

# Preprocess & chunk
preprocessed = preprocess_for_stt(file_path)
chunks = split_wav_to_chunks(preprocessed, chunk_sec=30, overlap_sec=1.5)

results = []
for chunk_path in chunks:
    audio_file = genai.upload_file(chunk_path)
    resp = model.generate_content([
        audio_file,
        "Please transcribe the content of this audio verbatim in the language spoken (Khmer). Translation is not required."
    ])
    results.append({"text": resp.text, "chunk_idx": idx})

combined = " ".join([r["text"] for r in results])
return combined, results
```

**Translation**:
```python
def translate_gemini_km_to_en(km_text: str) -> str:
    resp = model.generate_content(
        f"Translate the following Khmer text to English:\n\n{km_text}"
    )
    return resp.text
```

**Pros**:
- Free (with quota)
- Fast
- Good Khmer support

**Cons**:
- Less accurate than Whisper
- No confidence scores
- Requires chunking

### 3. AssemblyAI

**Function**: `transcribe_assemblyai_km_to_en(file_path: str) -> Tuple[str, str]`

**Implementation**:
```python
import assemblyai as aai

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Upload full file (no preprocessing)
with open(file_path, "rb") as f:
    upload_url = aai.Transcriber().upload_file(f)

# Configure
config = aai.TranscriptionConfig(
    language_code="km",  # Khmer
    language_detection=False,
    translation=True,
    translation_config=aai.TranslationConfig(target_languages=["en"])
)

# Transcribe (polling)
transcriber = aai.Transcriber()
transcript = transcriber.transcribe(upload_url, config=config)

# Wait for completion (up to 300s)
while transcript.status not in ["completed", "error"]:
    time.sleep(2)
    transcript = transcriber.get_transcript(transcript.id)

if transcript.status == "error":
    raise RuntimeError(f"Transcription failed: {transcript.error}")

stt_km = transcript.text
translated_en = transcript.translation["en"] if transcript.translation else ""

return stt_km, translated_en
```

**Pros**:
- Simultaneous translation (one API call)
- No chunking needed
- Very fast

**Cons**:
- Lower accuracy for Khmer
- Requires API key

### 4. Gladia

**Function**: `transcribe_gladia_km_to_en(file_path: str) -> Tuple[str, str]`

**Implementation**:
```python
import requests

# Upload
with open(file_path, "rb") as f:
    upload_resp = requests.post(
        "https://api.gladia.io/v2/upload",
        headers={"x-gladia-key": GLADIA_API_KEY},
        files={"audio": f}
    )
upload_url = upload_resp.json()["url"]

# Transcribe
transcribe_resp = requests.post(
    "https://api.gladia.io/v2/transcription",
    headers={"x-gladia-key": GLADIA_API_KEY},
    json={
        "audio_url": upload_url,
        "language": "km",
        "translation": True,
        "translation_config": {
            "target_languages": ["en"],
            "model": "base"
        }
    }
)

result_url = transcribe_resp.json()["result_url"]

# Poll for result
while True:
    result = requests.get(result_url).json()
    if result["status"] == "done":
        break
    time.sleep(3)

stt_km = result["transcription"]["text"]
translated_en = result["translation"]["en"]

return stt_km, translated_en
```

**Pros**:
- Simultaneous translation
- No chunking

**Cons**:
- Variable quality
- Complex error handling

### 5. ElevenLabs

**Function**: `transcribe_elevenlabs_km(file_path: str) -> str`

**Implementation**:
```python
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

with open(file_path, "rb") as f:
    transcript = client.audio.transcribe(
        audio=f,
        model="scribe_v1",
        language_code="khm",  # Khmer ISO 639-3
        diarize=False
    )

return transcript.text
```

**Pros**:
- Simple API
- Good Khmer support

**Cons**:
- No translation (Khmer output only)
- Requires separate translation step

### Recommendation

**Production**: Use **Google Gemini** (default)
- Free
- Good balance of speed and accuracy
- Integrated translation

**High accuracy needed**: Use **OpenAI Whisper**
- Best transcription quality
- Explicit prompt control

**Budget-conscious**: Use **AssemblyAI**
- Cheapest option
- Fast turnaround

---

## Categorization Logic

### Category Definitions

**File**: `impact_app/categorization/categorizer.py`

```python
CATEGORIES = [
    "0:Teacher/Methods",           # Comments on teaching methods/pedagogy
    "1:Mass Students",             # Comments on whole class
    "2a:Individual Character",     # Individual student's personality
    "2b:Individual Evaluation",    # Individual student's performance
    "2c:Individual Verification",  # Checking individual understanding
    "2d:Learning of how Student Learn",  # How students learn
    "fact:Mentioning facts"        # Factual observations
]
```

**Category Examples** (`seed_categories.json`):
```json
{
  "0:Teacher/Methods": [
    "The teacher used group discussion to engage students.",
    "Teacher explained the concept with visual aids."
  ],
  "1:Mass Students": [
    "All students participated actively.",
    "The class showed great enthusiasm."
  ],
  "2a:Individual Character": [
    "Sokha is very creative in problem-solving.",
    "Dara shows leadership qualities."
  ],
  "2b:Individual Evaluation": [
    "Channthy scored 85% on the quiz.",
    "Virak completed all assignments on time."
  ],
  "2c:Individual Verification": [
    "I confirmed that Sophea understands the lesson.",
    "Checked Pisey's homework - all correct."
  ],
  "2d:Learning of how Student Learn": [
    "Students learn better through hands-on activities.",
    "Visual learners benefit from diagrams."
  ],
  "fact:Mentioning facts": [
    "Today is Monday.",
    "The class has 30 students."
  ]
}
```

### Hybrid Classification Approach

**Function**: `categorize(text_en: str) -> Dict[str, Any]`

**Two-stage process**:

#### Stage 1: Embedding-Based Voting

```python
def _embed_vote(text_en: str, k: int = 5) -> Tuple[str, float, List[Dict]]:
    """
    Query ChromaDB for k nearest neighbors
    Vote by category, compute average similarity as confidence
    """
    results = _store.similarity_search_with_relevance_scores(text_en, k=5)

    counts = {c: [] for c in CATEGORIES}
    evidence = []

    for doc, score in results:
        cat = doc.metadata.get("category")
        counts[cat].append(float(score))
        evidence.append({
            "category": cat,
            "score": float(score),
            "example": doc.page_content[:300]
        })

    # Best = most votes, highest avg score
    best = max(CATEGORIES, key=lambda c: (
        len(counts[c]),
        sum(counts[c]) / len(counts[c]) if counts[c] else 0.0
    ))

    conf = (sum(counts[best]) / len(counts[best])) if counts[best] else 0.0
    return best, conf, evidence
```

**How it works**:
1. Embed input text using `text-embedding-3-small`
2. Query ChromaDB for 5 most similar examples
3. Group results by category
4. Select category with most votes
5. Confidence = average similarity score

**Example**:
```
Input: "Sokha is very creative and thinks outside the box"

Top 5 results:
[1] 2a:Individual Character (0.92) "Sokha is very creative..."
[2] 2a:Individual Character (0.88) "Dara shows leadership..."
[3] 0:Teacher/Methods (0.75) "Teacher used creative approach..."
[4] 2b:Individual Evaluation (0.68) "Student performed well..."
[5] 2a:Individual Character (0.65) "Pisey has unique perspective..."

Vote count:
2a:Individual Character: 3 votes, avg=0.85
0:Teacher/Methods: 1 vote, avg=0.75
2b:Individual Evaluation: 1 vote, avg=0.68

Winner: 2a:Individual Character (confidence=0.85)
```

#### Stage 2: LLM Refinement

```python
def _llm_refine(text_en: str, evidence: List[Dict]) -> Tuple[str, float, str]:
    """
    Present top 3 evidence to LLM for final decision
    """
    ev = "\n".join([
        f"[{i+1}] ({e['category']}, score={e['score']:.2f}) {e['example']}"
        for i, e in enumerate(evidence)
    ])

    system_prompt = (
        "You are a strict JSON-only classifier for teacher comments. "
        "Categories: " + ", ".join(CATEGORIES) + ". "
        "Return JSON: {\"category\":\"...\", \"confidence\":0~1, \"rationale\":\"...\"}."
    )

    user_prompt = (
        f"Nearest examples:\n{ev}\n\n"
        f"Classify the input into ONE category:\n---\n{text_en}\n---"
    )

    resp = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ])

    data = json.loads(resp.content)
    cat = data.get("category", "")
    conf = float(data.get("confidence", 0.0))
    rat = data.get("rationale", "")

    # Validate category
    if cat not in CATEGORIES:
        cat = evidence[0]["category"] if evidence else "None Evidence"

    return cat, conf, rat
```

**LLM Prompt Example**:
```
System:
You are a strict JSON-only classifier for teacher comments.
Categories: 0:Teacher/Methods, 1:Mass Students, 2a:Individual Character, 2b:Individual Evaluation, 2c:Individual Verification, 2d:Learning of how Student Learn, fact:Mentioning facts.
Return JSON: {"category":"...", "confidence":0~1, "rationale":"..."}.

User:
Nearest examples:
[1] (2a:Individual Character, score=0.92) Sokha is very creative in problem-solving.
[2] (2a:Individual Character, score=0.88) Dara shows leadership qualities.
[3] (0:Teacher/Methods, score=0.75) The teacher used creative approach to engage students.

Classify the input into ONE category:
---
Sokha thinks outside the box and comes up with unique solutions
---
```

**LLM Response**:
```json
{
  "category": "2a:Individual Character",
  "confidence": 0.95,
  "rationale": "The comment focuses on Sokha's specific personality trait (creative thinking) rather than performance or the teacher's method. The phrase 'thinks outside the box' describes character, not achievement."
}
```

### Final Output

```python
def categorize(text_en: str) -> Dict[str, Any]:
    base_cat, conf_embed, ev = _embed_vote(text_en, k=5)

    if CATEGORY_MODE == "embed":
        return {
            "category": base_cat,
            "confidence": conf_embed,
            "evidence": ev,
            "rationale": "embed_only"
        }

    # Hybrid mode (default)
    cat, conf_llm, rat = _llm_refine(text_en, ev[:3])
    final_cat = cat or base_cat
    final_conf = max(conf_embed, conf_llm) if conf_llm else conf_embed

    return {
        "category": final_cat,
        "confidence": float(final_conf),
        "evidence": ev[:3],
        "rationale": rat
    }
```

**Output Structure**:
```python
{
  "category": "2a:Individual Character",
  "confidence": 0.95,
  "evidence": [
    {
      "category": "2a:Individual Character",
      "score": 0.92,
      "example": "Sokha is very creative in problem-solving."
    },
    {
      "category": "2a:Individual Character",
      "score": 0.88,
      "example": "Dara shows leadership qualities."
    },
    {
      "category": "0:Teacher/Methods",
      "score": 0.75,
      "example": "The teacher used creative approach..."
    }
  ],
  "rationale": "The comment focuses on Sokha's specific personality trait..."
}
```

### Configuration

**Environment Variables**:
```bash
CATEGORY_MODE=hybrid  # "embed" or "hybrid"
CHROMA_DIR=.chroma_categories
CATEGORY_SEED_PATH=seed_categories.json
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini
```

**Mode Comparison**:
| Mode | Speed | Accuracy | Explainability | Cost |
|------|-------|----------|----------------|------|
| `embed` | Fast | Good | Evidence only | Low (embedding only) |
| `hybrid` | Moderate | Excellent | Evidence + rationale | Medium (embedding + LLM) |

---

## Training Space Management

### Registry File

**Location**: `project/.runtime/chat_registry.json`

**Purpose**: Map Telegram chat IDs to Notion page/DB IDs

**Structure**:
```json
{
  "<chat_id>": {
    "training_page_id": "<page_id>",
    "training_db_id": "<db_id>",
    "training_name": "<name>"
  }
}
```

**Example**:
```json
{
  "-4891823124": {
    "training_page_id": "2b34423b-0fc4-81c1-b070-c3e7ad5f0f38",
    "training_db_id": "2b34423b-0fc4-81c1-b2de-c375975c3c50",
    "training_name": "TVETSCHOOL_JAN2026"
  },
  "-1234567890": {
    "training_page_id": "abc123...",
    "training_db_id": "def456...",
    "training_name": "ELEMENTARY_MATH_TRAINING"
  }
}
```

### Auto-Creation Logic

**Function**: `ensure_training_space(chat_id: int, training_name: str) -> Tuple[str, str]`
**File**: `impact_app/notion/notion_client.py`

```python
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / ".runtime" / "chat_registry.json"

def ensure_training_space(chat_id: int, training_name: str) -> Tuple[str, str]:
    """
    Ensure Training page and DB exist for this chat.
    Returns: (training_page_id, training_db_id)
    """
    # Load registry
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "r") as f:
            registry = json.load(f)
    else:
        registry = {}

    key = str(chat_id)

    # Return if exists
    if key in registry:
        return registry[key]["training_page_id"], registry[key]["training_db_id"]

    # Create new Training space
    page_id = _make_training_page(training_name)
    db_id = _make_child_database(page_id)

    # Save to registry
    registry[key] = {
        "training_page_id": page_id,
        "training_db_id": db_id,
        "training_name": training_name
    }
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    return page_id, db_id
```

### Page Creation

```python
def _make_training_page(training_name: str) -> str:
    """Create a new page under Root Page"""
    page = notion.pages.create(
        parent={"page_id": NOTION_ROOT_PAGE_ID},
        properties={
            "title": [{"text": {"content": training_name}}]
        }
    )
    return page["id"]
```

### Database Creation

```python
def _make_child_database(parent_page_id: str) -> str:
    """Create inline database in the Training page"""
    db = notion.databases.create(
        parent={"page_id": parent_page_id},
        title=[{"text": {"content": "Training Records"}}],
        properties={
            "Name": {"title": {}},
            "Date": {"date": {}},
            "STT_Km": {"rich_text": {}},
            "Translated_En": {"rich_text": {}},
            "Category": {
                "select": {
                    "options": [
                        {"name": "0:Teacher/Methods", "color": "blue"},
                        {"name": "1:Mass Students", "color": "green"},
                        {"name": "2a:Individual Character", "color": "yellow"},
                        {"name": "2b:Individual Evaluation", "color": "orange"},
                        {"name": "2c:Individual Verification", "color": "red"},
                        {"name": "2d:Learning of how Student Learn", "color": "purple"},
                        {"name": "fact:Mentioning facts", "color": "gray"}
                    ]
                }
            },
            "CategoryConfidence": {"number": {}},
            "AudioURL": {"url": {}},
            "ChatID": {"number": {}},
            "MessageID": {"number": {}},
            "ExternalID": {"rich_text": {}}
        }
    )
    return db["id"]
```

---

## Code Reference

### Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `impact_app/service.py` | Main service logic | 133 |
| `core/audio/audio_preprocess.py` | Preprocessing pipeline | ~200 |
| `core/audio/stt_translate.py` | STT & translation | ~500 |
| `core/audio/stt_chunking.py` | Audio chunking | ~100 |
| `impact_app/categorization/categorizer.py` | Hybrid classification | 131 |
| `impact_app/notion/notion_client.py` | Notion operations | ~200 |

### Key Functions

#### `impact_process_update(update: dict) -> None`
**File**: `impact_app/service.py:21`

Main entry point for Impact webhook.

**Error Handling**:
- All exceptions logged
- User-friendly Telegram messages sent on failure
- Always returns (200 OK to Telegram)

---

#### `preprocess_for_stt(src_path: str, vad_aggr: int = 2) -> str`
**File**: `core/audio/audio_preprocess.py:112`

7-stage preprocessing pipeline.

**Returns**: Path to preprocessed WAV file

---

#### `categorize(text_en: str) -> Dict[str, Any]`
**File**: `impact_app/categorization/categorizer.py:93`

Hybrid embedding + LLM classification.

**Returns**:
```python
{
  "category": str,
  "confidence": float,
  "evidence": List[Dict],
  "rationale": str
}
```

---

## Next Steps

- API reference: [06_api_reference.md](06_api_reference.md)
- Troubleshooting: [07_troubleshooting.md](07_troubleshooting.md)
- Back to overview: [01_overview.md](01_overview.md)
