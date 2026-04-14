# API Reference

## Table of Contents
- [FastAPI Endpoints](#fastapi-endpoints)
- [Core Functions](#core-functions)
- [Notion API Patterns](#notion-api-patterns)
- [Telegram API Patterns](#telegram-api-patterns)
- [Audio Processing Functions](#audio-processing-functions)

---

## FastAPI Endpoints

### Health Check

```http
GET /healthz
```

**Purpose**: Verify that the application is running

**Request**: None

**Response**:
```json
{
  "ok": true,
  "time": "2026-01-03T10:30:00.123456+00:00"
}
```

**Status Codes**:
- `200 OK`: Application is running

**Implementation**:
```python
# project/main.py:23
@app.get('/healthz')
def healthz():
    return {'ok': True, 'time': datetime.now(timezone.utc).isoformat()}
```

---

### Narrative Bot Webhook

```http
POST /telegram/narrative/webhook
```

**Purpose**: Receive Telegram updates for Narrative Bot

**Headers**:
```
Content-Type: application/json
X-Telegram-Bot-Api-Secret-Token: <NARRATIVE_TELEGRAM_SECRET_TOKEN>
```

**Request Body** (Telegram Update):
```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 456,
    "from": {
      "id": 123456789,
      "first_name": "John",
      "last_name": "Doe",
      "username": "johndoe"
    },
    "chat": {
      "id": -987654321,
      "title": "School A - Grade 5",
      "type": "group"
    },
    "date": 1735902600,
    "text": "Today we practiced multiplication tables"
  }
}
```

**Response**:
```json
{
  "ok": true
}
```

**Status Codes**:
- `200 OK`: Update received (always returned, even if processing fails)
- `401 Unauthorized`: Invalid secret token

**Processing**:
- Update is processed in background task
- Telegram receives immediate ACK (prevents timeout/retry)

**Implementation**:
```python
# project/main.py:37
@app.post('/telegram/narrative/webhook')
async def narrative_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != NARRATIVE_TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid secret Token")
    update = await request.json()
    background.add_task(handle_telegram_update, update)
    return JSONResponse({"ok": True})
```

---

### Impact Bot Webhook

```http
POST /telegram/impact/webhook
```

**Purpose**: Receive Telegram updates for Impact Bot

**Headers**:
```
Content-Type: application/json
X-Telegram-Bot-Api-Secret-Token: <IMPACT_TELEGRAM_SECRET_TOKEN>
```

**Request Body** (Telegram Update):
```json
{
  "update_id": 987654321,
  "message": {
    "message_id": 789,
    "from": {
      "id": 111222333,
      "first_name": "Trainer",
      "username": "trainer_jane"
    },
    "chat": {
      "id": -444555666,
      "title": "TVET Training Jan 2026",
      "type": "group"
    },
    "date": 1735902700,
    "voice": {
      "file_id": "AwACAgQAAxkBAAIBB2...",
      "file_unique_id": "AgADyQEAAqKfZA",
      "duration": 45,
      "mime_type": "audio/ogg"
    }
  }
}
```

**Response**:
```json
{
  "ok": true
}
```

**Status Codes**:
- `200 OK`: Update received
- `401 Unauthorized`: Invalid secret token

**Implementation**:
```python
# project/main.py:27
@app.post('/telegram/impact/webhook')
async def impact_webhook(request: Request, background: BackgroundTasks):
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != IMPACT_TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail='Invalid secret token')
    update = await request.json()
    background.add_task(impact_process_update, update)
    return JSONResponse({'ok': True})
```

---

## Core Functions

### Telegram Helper Functions

#### `tg_api(method: str, token: str, **params) -> dict`

**Purpose**: Generic Telegram API call wrapper

**Parameters**:
- `method` (str): API method name (e.g., "getFile", "sendMessage")
- `token` (str): Bot token
- `**params`: Method-specific parameters

**Returns**: JSON response from Telegram API

**Raises**: `requests.HTTPError` if status code is not 200

**Example**:
```python
# core/telegram_helper.py
result = tg_api("getFile", bot_token, file_id="AwACAgQAAxkBAAIBB2...")
file_path = result["result"]["file_path"]
```

---

#### `tg_get_file_url(file_id: str, token: str) -> str`

**Purpose**: Convert Telegram file_id to downloadable URL

**Parameters**:
- `file_id` (str): Telegram file ID
- `token` (str): Bot token

**Returns**: Full download URL

**Example**:
```python
url = tg_get_file_url("AwACAgQAAxkBAAIBB2...", bot_token)
# Returns: "https://api.telegram.org/file/bot<token>/voice/file_123.ogg"
```

**Implementation**:
```python
def tg_get_file_url(file_id: str, token: str) -> str:
    result = tg_api("getFile", token, file_id=file_id)
    file_path = result["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{token}/{file_path}"
```

---

#### `tg_send_message(chat_id: int, token: str, text: str) -> None`

**Purpose**: Send text message to Telegram chat

**Parameters**:
- `chat_id` (int): Target chat ID
- `token` (str): Bot token
- `text` (str): Message text

**Returns**: None (logs warning on failure)

**Example**:
```python
tg_send_message(-987654321, bot_token, "Processing complete!")
```

**Implementation**:
```python
def tg_send_message(chat_id: int, token: str, text: str) -> None:
    try:
        tg_api("sendMessage", token, chat_id=chat_id, text=text)
    except Exception as e:
        logger.warning(f"Failed to send message: {e}")
```

---

#### `new_id() -> str`

**Purpose**: Generate ULID (Universally Unique Lexicographically Sortable Identifier)

**Returns**: ULID string (26 characters, timestamp-sortable)

**Example**:
```python
external_id = new_id()
# Returns: "01HQJK3M5N6P7Q8R9S0TVWXY1Z"
```

**Implementation**:
```python
import ulid

def new_id() -> str:
    return str(ulid.ULID())
```

---

### Thread Lock Functions

#### `get_teacher_lock(teacher_page_id: str) -> threading.Lock`

**Purpose**: Get or create a thread lock for a specific teacher

**Parameters**:
- `teacher_page_id` (str): Notion teacher page ID

**Returns**: `threading.Lock` instance

**Usage**:
```python
teacher_lock = get_teacher_lock(teacher_id)
with teacher_lock:
    # Thread-safe operations on teacher's Narratives
    result = decide_and_get_narrative(...)
```

**Implementation**:
```python
# core/locks.py
_teacher_locks: Dict[str, threading.Lock] = {}
_teacher_locks_guard = threading.Lock()

def get_teacher_lock(teacher_page_id: str) -> threading.Lock:
    with _teacher_locks_guard:
        if teacher_page_id not in _teacher_locks:
            _teacher_locks[teacher_page_id] = threading.Lock()
    return _teacher_locks[teacher_page_id]
```

---

### Audio Processing Functions

#### `preprocess_for_stt(src_path: str, vad_aggr: int = 2) -> str`

**Purpose**: Comprehensive audio preprocessing for STT

**Parameters**:
- `src_path` (str): Path to input audio file
- `vad_aggr` (int): VAD aggressiveness (0-3, default 2)

**Returns**: Path to preprocessed 16kHz mono WAV file

**Pipeline**:
1. Convert to 16kHz mono WAV
2. Noise reduction
3. Bandpass filter (70Hz HPF, 7kHz LPF)
4. EQ peaking (700Hz +2.5dB, 1500Hz +2.0dB)
5. Peak normalization (-1dBFS)
6. AGC & compression (target RMS -20dB)
7. VAD trimming

**Example**:
```python
preprocessed = preprocess_for_stt("input.mp3", vad_aggr=2)
# Returns: "/tmp/tmpXXX/preprocessed.wav"
```

---

#### `split_wav_to_chunks(wav_path: str, chunk_sec: float = 30.0, overlap_sec: float = 1.5) -> List[str]`

**Purpose**: Split audio into overlapping chunks for STT

**Parameters**:
- `wav_path` (str): Path to WAV file
- `chunk_sec` (float): Chunk duration in seconds (default 30)
- `overlap_sec` (float): Overlap duration (default 1.5)

**Returns**: List of paths to chunk files

**Example**:
```python
chunks = split_wav_to_chunks("audio.wav", chunk_sec=30, overlap_sec=1.5)
# Returns: ["/tmp/chunk_000.wav", "/tmp/chunk_001.wav", ...]
```

**Logic**:
```
Audio: [========================================] (90 seconds)
Chunks:
  [0-30s]
       [28.5-58.5s]
              [57-87s]
                     [85.5-90s]
```

---

#### `oai_transcribe(file_path: str) -> Tuple[str, float]`

**Purpose**: Transcribe audio using OpenAI Whisper

**Parameters**:
- `file_path` (str): Path to audio file

**Returns**: Tuple of (transcript text, average confidence)

**Example**:
```python
text, confidence = oai_transcribe("audio.wav")
# Returns: ("សួស្តី ខ្ញុំឈ្មោះ...", 0.95)
```

---

#### `oai_translate_km_to_en(km_text: str) -> Tuple[str, str]`

**Purpose**: Translate Khmer text to English using OpenAI

**Parameters**:
- `km_text` (str): Khmer text

**Returns**: Tuple of (English translation, source language)

**Example**:
```python
en_text, src_lang = oai_translate_km_to_en("សួស្តី")
# Returns: ("Hello", "km")
```

---

#### `decide_transcribe_model(file_path: str, engine: str = "gemini") -> Tuple[str, str]`

**Purpose**: Transcribe and translate using specified engine

**Parameters**:
- `file_path` (str): Path to audio file
- `engine` (str): Engine name ("oai", "gemini", "assemblyai", "gladia", "elevenlabs")

**Returns**: Tuple of (Khmer transcript, English translation)

**Example**:
```python
km_text, en_text = decide_transcribe_model("audio.mp3", engine="gemini")
```

---

### Categorization Functions

#### `categorize(text_en: str) -> Dict[str, Any]`

**Purpose**: Classify text into category using hybrid approach

**Parameters**:
- `text_en` (str): English text to categorize

**Returns**: Dictionary with category, confidence, evidence, rationale

**Example**:
```python
result = categorize("Sokha is very creative and thinks outside the box")
# Returns:
# {
#   "category": "2a:Individual Character",
#   "confidence": 0.95,
#   "evidence": [
#     {"category": "2a:Individual Character", "score": 0.92, "example": "..."},
#     ...
#   ],
#   "rationale": "The comment focuses on Sokha's personality trait..."
# }
```

---

## Notion API Patterns

### Query Database with Filter

**Pattern**: Find pages by property value

**Example**: Find School by Telegram Chat ID
```python
from core.notion_client import get_notion_client
notion = get_notion_client()

results = notion.databases.query(
    database_id=NOTION_SCHOOLS_DB_ID,
    filter={
        "property": "Telegram Chat ID",
        "number": {"equals": chat_id}
    }
)

if results["results"]:
    school_page_id = results["results"][0]["id"]
```

**Filter Types**:
| Property Type | Filter Example |
|--------------|----------------|
| Number | `{"number": {"equals": 123}}` |
| Rich Text | `{"rich_text": {"contains": "text"}}` |
| Select | `{"select": {"equals": "Option"}}` |
| Checkbox | `{"checkbox": {"equals": True}}` |
| Date | `{"date": {"after": "2026-01-01T00:00:00Z"}}` |
| Relation | `{"relation": {"contains": "page_id"}}` |

---

### Create Page in Database

**Pattern**: Insert new record

**Example**: Create new Narrative
```python
page = notion.pages.create(
    parent={"database_id": NOTION_NARRATIVES_DB_ID},
    properties={
        "Title": {"title": [{"text": {"content": "New Practice"}}]},
        "Teacher": {"relation": [{"id": teacher_page_id}]},
        "School": {"relation": [{"id": school_page_id}]},
        "Date": {"date": {"start": "2026-01-03T10:30:00Z"}},
        "Is Closed": {"checkbox": False}
    }
)
narrative_page_id = page["id"]
```

**Property Formats**:
| Type | Format |
|------|--------|
| Title | `{"title": [{"text": {"content": "..."}}]}` |
| Rich Text | `{"rich_text": [{"text": {"content": "..."}}]}` |
| Number | `{"number": 123}` |
| Select | `{"select": {"name": "Option"}}` |
| Checkbox | `{"checkbox": True}` |
| Date | `{"date": {"start": "2026-01-03T10:30:00Z"}}` |
| Relation | `{"relation": [{"id": "page_id"}]}` |
| URL | `{"url": "https://..."}` |
| Files | `{"files": [{"name": "...", "external": {"url": "..."}}]}` |

---

### Update Page Properties

**Pattern**: Modify existing page

**Example**: Close Narrative
```python
notion.pages.update(
    page_id=narrative_page_id,
    properties={
        "Is Closed": {"checkbox": True},
        "Date": {
            "date": {
                "start": start_iso,
                "end": end_iso
            }
        }
    }
)
```

---

### Append Child Blocks

**Pattern**: Add content blocks to page

**Example**: Add Summary and Detailed Content
```python
blocks = [
    {
        "type": "heading_2",
        "heading_2": {"rich_text": [{"text": {"content": "Summary"}}]}
    },
    {
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {"content": summary_text}}]}
    },
    {
        "type": "heading_2",
        "heading_2": {"rich_text": [{"text": {"content": "Detailed Content"}}]}
    },
    {
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {"content": detailed_text}}]}
    }
]

notion.blocks.children.append(
    block_id=narrative_page_id,
    children=blocks
)
```

**Block Types**:
| Type | Structure |
|------|-----------|
| Heading 1 | `{"type": "heading_1", "heading_1": {"rich_text": [...]}}` |
| Heading 2 | `{"type": "heading_2", "heading_2": {"rich_text": [...]}}` |
| Heading 3 | `{"type": "heading_3", "heading_3": {"rich_text": [...]}}` |
| Paragraph | `{"type": "paragraph", "paragraph": {"rich_text": [...]}}` |
| Image | `{"type": "image", "image": {"external": {"url": "..."}}}` |
| Video | `{"type": "video", "video": {"external": {"url": "..."}}}` |

---

### Rich Text Character Limit

**Notion Limit**: 2000 characters per rich_text array

**Solution**: Chunk text into multiple parts

**Function**:
```python
def text_to_rich_text_blocks(text: str, chunk: int = 1900) -> List[dict]:
    """
    Split text into chunks to avoid 2000-char limit

    Args:
        text: Text to split
        chunk: Max chars per chunk (default 1900, leaves margin)

    Returns:
        List of rich_text objects
    """
    s = (text or "")
    parts = [s[i:i+chunk] for i in range(0, len(s), chunk)] or [""]
    return [{"type": "text", "text": {"content": p}} for p in parts]
```

**Example**:
```python
long_text = "..." * 5000  # 15000 characters

props = {
    "Translated_En": {
        "rich_text": text_to_rich_text_blocks(long_text, chunk=1900)
    }
}
```

---

## Telegram API Patterns

### Set Webhook

**API Call**:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/telegram/narrative/webhook",
    "secret_token": "<SECRET_TOKEN>"
  }'
```

**Response**:
```json
{
  "ok": true,
  "result": true,
  "description": "Webhook was set"
}
```

---

### Get Webhook Info

**API Call**:
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

**Response**:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com/telegram/narrative/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "max_connections": 40,
    "ip_address": "1.2.3.4"
  }
}
```

---

### Get File

**API Call**:
```bash
curl "https://api.telegram.org/bot<TOKEN>/getFile?file_id=<FILE_ID>"
```

**Response**:
```json
{
  "ok": true,
  "result": {
    "file_id": "AwACAgQAAxkBAAIBB2...",
    "file_unique_id": "AgADyQEAAqKfZA",
    "file_size": 45678,
    "file_path": "voice/file_123.ogg"
  }
}
```

**Download URL**:
```
https://api.telegram.org/file/bot<TOKEN>/voice/file_123.ogg
```

---

### Send Message

**API Call**:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": -987654321,
    "text": "Processing complete!"
  }'
```

---

## Audio Processing Functions

### Noise Reduction

```python
import noisereduce as nr

y = nr.reduce_noise(
    y=audio_data,        # numpy array
    sr=sample_rate,      # sampling rate (Hz)
    prop_decrease=0.6,   # reduction amount (0-1)
    stationary=True      # assume constant noise
)
```

---

### Butterworth Filter

```python
from scipy.signal import butter, sosfiltfilt

# Design filter
sos = butter(
    N=4,                 # filter order
    Wn=[70/(sr/2), 7000/(sr/2)],  # normalized cutoffs
    btype="bandpass",
    output="sos"         # second-order sections
)

# Apply filter (zero-phase)
y_filtered = sosfiltfilt(sos, y)
```

---

### VAD (Voice Activity Detection)

```python
import webrtcvad

vad = webrtcvad.Vad(2)  # aggressiveness 0-3

frame_duration_ms = 20  # 10, 20, or 30 ms
frame_len = int(sr * frame_duration_ms / 1000)

# Convert to 16-bit PCM
pcm16 = (audio_data * 32767).astype(np.int16).tobytes()

# Process frames
for i in range(0, len(pcm16), frame_len * 2):
    chunk = pcm16[i:i + frame_len * 2]
    is_speech = vad.is_speech(chunk, sample_rate=sr)
```

---

## Next Steps

- Troubleshooting guide: [07_troubleshooting.md](07_troubleshooting.md)
- Back to overview: [01_overview.md](01_overview.md)
