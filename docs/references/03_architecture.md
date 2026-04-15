# System Architecture

## Table of Contents
- [Directory Structure](#directory-structure)
- [Module Dependencies](#module-dependencies)
- [Data Flow](#data-flow)
- [Key Design Patterns](#key-design-patterns)
- [Database Schema](#database-schema)

---

## Directory Structure

```
impact_db/
├── README.md                           # Project overview
├── requirements.txt                    # Python dependencies
├── .env                                # Environment variables (gitignored)
├── .gitignore                          # Git ignore rules
├── Dockerfile                          # Docker image definition
├── docker-compose.yml                  # Docker Compose config
│
├── impact_db_env/                      # Python virtual environment (gitignored)
│
├── docs/                               # Documentation (this folder)
│   ├── 01_overview.md
│   ├── 02_setup.md
│   ├── 03_architecture.md
│   ├── 04_narrative_db.md
│   ├── 05_impact_db.md
│   ├── 06_api_reference.md
│   └── 07_troubleshooting.md
│
└── project/                            # Main application code
    ├── main.py                         # FastAPI entry point
    │
    ├── core/                           # Core shared modules
    │   ├── __init__.py
    │   ├── config.py                   # Environment variable loader
    │   ├── locks.py                    # Thread-safe lock management
    │   ├── notion_client.py            # Notion API client
    │   ├── telegram_helper.py          # Telegram API helpers
    │   └── audio/                      # Audio processing modules
    │       ├── __init__.py
    │       ├── audio_preprocess.py     # Audio preprocessing pipeline
    │       ├── helpers_audio.py        # Audio utilities
    │       ├── stt_chunking.py         # Audio chunking for STT
    │       └── stt_translate.py        # STT & translation engines
    │
    ├── narrative_app/                  # Narrative DB service
    │   ├── __init__.py
    │   ├── service.py                  # Main service logic
    │   ├── grouping.py                 # Time window logic
    │   ├── classification.py           # Subject tag classification
    │   ├── summarization.py            # LLM summarization
    │   ├── service_staff_narrative.py  # Staff Narrative sync
    │   └── notion_repos/               # Notion repository layer
    │       ├── notion_repos.py         # Main Notion operations
    │       ├── subjects_repos.py       # Subject DB operations
    │       └── notion_staff_repos.py   # Staff Narrative operations
    │
    ├── impact_app/                     # Impact DB service
    │   ├── __init__.py
    │   ├── service.py                  # Main service logic
    │   ├── categorization/             # Category classification
    │   │   └── categorizer.py          # Hybrid embedding + LLM
    │   └── notion/                     # Notion operations
    │       └── notion_client.py        # Impact-specific Notion logic
    │
    ├── .runtime/                       # Runtime data (gitignored)
    │   └── chat_registry.json          # Training chat → Notion DB mapping
    │
    ├── .chroma_categories/             # ChromaDB storage (gitignored)
    │   └── chroma.sqlite3              # Vector embeddings
    │
    └── seed_categories.json            # Category seed data
```

---

## Module Dependencies

### Dependency Graph

```
main.py
├─── narrative_app.service
│    ├─── core.config
│    ├─── core.locks
│    ├─── core.telegram_helper
│    ├─── core.audio.helpers_audio
│    ├─── core.audio.stt_translate
│    ├─── narrative_app.grouping
│    ├─── narrative_app.classification
│    ├─── narrative_app.summarization
│    ├─── narrative_app.service_staff_narrative
│    │    ├─── narrative_app.notion_repos.subjects_repos
│    │    └─── narrative_app.notion_repos.notion_staff_repos
│    └─── narrative_app.notion_repos.notion_repos
│         └─── core.notion_client
│
└─── impact_app.service
     ├─── core.config
     ├─── core.telegram_helper
     ├─── core.audio.helpers_audio
     ├─── core.audio.stt_translate
     ├─── core.audio.stt_chunking
     ├─── core.audio.audio_preprocess
     ├─── impact_app.categorization.categorizer
     │    └─── (ChromaDB, LangChain, OpenAI)
     └─── impact_app.notion.notion_client
          └─── core.notion_client
```

### Module Responsibilities

#### `project/main.py`
- FastAPI application initialization
- Webhook endpoints (`/telegram/narrative/webhook`, `/telegram/impact/webhook`)
- Health check endpoint (`/healthz`)
- Background task orchestration

#### `project/core/`
**config.py**
- Load environment variables from `.env`
- Provide typed configuration objects
- Validate required environment variables

**locks.py**
- Manage per-teacher thread locks
- Ensure thread-safe Narrative operations
- Prevent race conditions in concurrent message handling

**notion_client.py**
- Initialize Notion client with API key
- Shared singleton for all Notion operations

**telegram_helper.py**
- Generic Telegram API call wrapper (`tg_api`)
- File URL retrieval (`tg_get_file_url`)
- Message sending (`tg_send_message`)
- ULID generation (`new_id`)

**audio/** subdirectory
- `audio_preprocess.py`: Noise reduction, filtering, normalization, VAD
- `helpers_audio.py`: Audio file utilities
- `stt_chunking.py`: Split audio into 30-second chunks with overlap
- `stt_translate.py`: Multi-engine STT (OpenAI, Gemini, AssemblyAI, Gladia, ElevenLabs) and translation

#### `project/narrative_app/`
**service.py**
- Main entry point: `handle_telegram_update(update: dict)`
- School/Teacher resolution
- Message type detection (text/voice/photo/video)
- Narrative creation/appending logic
- Media file handling

**grouping.py**
- Time window configuration (`NARRATIVE_WINDOW_MINUTES`)
- Window boundary calculation (`is_within_window`)

**classification.py**
- Subject tag classification using OpenAI GPT-4
- Returns one of: `["Khmer", "Math", "Science", "PE", "IT", "Reginal Lifeskill Program", "None"]`

**summarization.py**
- `generate_summary()`: Brief 3-6 sentence summary
- `generate_detailed_content()`: Detailed lesson breakdown

**service_staff_narrative.py**
- Sync closed Narratives to Staff Narrative DB
- Update `Last Practice At`, `Latest Narrative`, `Subject Tag` relations

**notion_repos/** subdirectory
- Repository pattern for Notion DB operations
- Abstraction layer over Notion API
- `notion_repos.py`: Schools, Teachers, Narratives CRUD
- `subjects_repos.py`: Subject DB operations
- `notion_staff_repos.py`: Staff Narrative DB operations

#### `project/impact_app/`
**service.py**
- Main entry point: `impact_process_update(update: dict)`
- Training space management (chat_registry.json)
- Audio download and preprocessing orchestration
- STT engine selection (`decide_transcribe_model`)
- Categorization and Notion storage

**categorization/categorizer.py**
- `categorize(text: str) -> dict`: Hybrid classification
- Embedding-based voting (ChromaDB + OpenAI embeddings)
- LLM refinement (GPT-4o-mini)
- Returns: `{category, confidence, evidence, rationale}`

**notion/notion_client.py**
- Training page/DB creation (`_make_training_page`, `_make_child_database`)
- Impact record creation (`create_or_update_notion_page`)
- ExternalID-based deduplication

---

## Data Flow

### Narrative DB Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Telegram Message Received                                │
│    {message: {text/voice/photo/video, from, chat, date}}    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Extract Metadata                                          │
│    - chat_info: {id, title, type}                            │
│    - user_info: {id, first_name, last_name, username}        │
│    - timestamp (UTC)                                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Resolve School & Teacher                                  │
│    resolve_school(chat_info)                                 │
│      → Notion query by Telegram Chat ID                      │
│      → Create if not exists                                  │
│    resolve_teacher(user_info, school_id)                     │
│      → Notion query by Telegram User ID                      │
│      → Create if not exists                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Process Message Content                                   │
│    - Text: oai_translate_km_to_en() if needed                │
│    - Voice: oai_transcribe() → oai_translate_km_to_en()      │
│    - Photo/Video: Extract file_id, convert to URL            │
│    - Document: Check if audio, process accordingly           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Decide Narrative (with Thread Lock)                       │
│    acquire_teacher_lock(teacher_page_id)                     │
│      ↓                                                        │
│    query_open_narratives(teacher_id)                         │
│      ↓                                                        │
│    ├─ No open Narrative → create_narrative()                 │
│    ├─ Within time window → append_and_update_narrative()     │
│    └─ Outside time window → close_narrative()                │
│                              ├─ generate_summary()            │
│                              ├─ generate_detailed_content()   │
│                              ├─ enrich_narrative_with_tags() │
│                              └─ sync_staff_narrative()        │
│                            → create_narrative()               │
│      ↓                                                        │
│    release_teacher_lock(teacher_page_id)                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Append Media (if any)                                     │
│    for each photo/video:                                     │
│      - Convert file_id to URL                                │
│      - Append to Narrative.Media property                    │
│      - Add image/video block to page children                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Return 200 OK to Telegram                                 │
└─────────────────────────────────────────────────────────────┘
```

### Impact DB Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Telegram Audio Message Received                           │
│    {message: {voice/audio/document, from, chat, date}}       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Extract Audio File Info                                   │
│    pick_audio_from_message()                                 │
│      → {file_id, duration, mime_type}                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Ensure Training Space                                     │
│    ensure_training_space(chat_id, training_name)             │
│      ├─ Load chat_registry.json                              │
│      ├─ If exists: return (page_id, db_id)                   │
│      └─ If not exists:                                       │
│          ├─ _make_training_page(training_name)               │
│          ├─ _make_child_database(page_id)                    │
│          └─ Save to chat_registry.json                       │
└────────────────────────┬─────────────────���──────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Download & Preprocess Audio                               │
│    tg_get_file_url(file_id) → download to temp file          │
│      ↓                                                        │
│    decide_transcribe_model(file_path, engine="gemini")       │
│      ├─ preprocess_for_stt(file_path)                        │
│      │    ├─ Convert to 16kHz mono WAV                       │
│      │    ├─ Noise reduction (noisereduce)                   │
│      │    ├─ Bandpass filter (70Hz HPF, 7kHz LPF)            │
│      │    ├─ EQ peaking (700Hz +2.5dB, 1500Hz +2.0dB)        │
│      │    ├─ Peak normalization (-1dBFS)                     │
│      │    ├─ AGC & compression (target RMS -20dB)            │
│      │    └─ VAD trimming (webrtcvad)                        │
│      ├─ split_wav_to_chunks(file, chunk_sec=30, overlap=1.5) │
│      └─ For each chunk:                                      │
│          ├─ transcribe_gemini_km() → stt_km                  │
│          └─ translate_gemini_km_to_en() → translated_en      │
│      → Combine chunks by timestamp                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Categorize                                                │
│    categorize(translated_en)                                 │
│      ├─ _embed_vote(text):                                   │
│      │    ├─ Query ChromaDB (k=5 nearest neighbors)          │
│      │    └─ Vote by category, compute avg similarity        │
│      └─ _llm_refine(text, evidence):                         │
│           ├─ Prompt GPT-4o-mini with top 3 evidence          │
│           └─ Return {category, confidence, rationale}        │
│    → {category, confidence, evidence, rationale}             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Save to Notion                                            │
│    create_or_update_notion_page(training_db_id, ...)         │
│      ├─ Check if page exists by ExternalID                   │
│      ├─ Create/update page with properties:                  │
│      │    - Name, Date, STT_Km, Translated_En                │
│      │    - Category, CategoryConfidence                     │
│      │    - AudioURL, ChatID, MessageID, ExternalID          │
│      └─ Append child blocks:                                 │
│           ├─ "Transcript (KM)" heading + paragraphs          │
│           ├─ "Translation (EN)" heading + paragraphs (1900ch)│
│           ├─ "Category Evidence" + evidence list             │
│           └─ "Rationale: ..." paragraph                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Send Telegram Notification                                │
│    tg_send_message(chat_id, "Processing complete")           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. Return 200 OK to Telegram                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Design Patterns

### 1. Repository Pattern

**Purpose**: Abstract Notion API operations

**Example**: `narrative_app/notion_repos/notion_repos.py`

```python
def get_or_create_school_by_chat(chat_info: dict) -> str:
    """
    Query Schools DB by Telegram Chat ID.
    If not found, create a new school page.
    Returns: school_page_id
    """
    # Query logic
    # Creation logic
    return school_page_id
```

**Benefits**:
- Clean separation of concerns
- Easy to mock for testing
- Centralized Notion API error handling

### 2. Background Task Pattern

**Purpose**: Return 200 OK to Telegram immediately, process in background

**Example**: `project/main.py`

```python
@app.post('/telegram/narrative/webhook')
async def narrative_webhook(request: Request, background: BackgroundTasks):
    update = await request.json()
    background.add_task(handle_telegram_update, update)
    return JSONResponse({"ok": True})
```

**Benefits**:
- Prevent Telegram timeout (60 seconds)
- Avoid duplicate message delivery
- Graceful handling of long-running tasks

### 3. Thread Lock Pattern

**Purpose**: Prevent race conditions when multiple messages arrive simultaneously

**Example**: `core/locks.py`

```python
_teacher_locks: Dict[str, threading.Lock] = {}
_teacher_locks_guard = threading.Lock()

def acquire_teacher_lock(teacher_page_id: str) -> threading.Lock:
    with _teacher_locks_guard:
        if teacher_page_id not in _teacher_locks:
            _teacher_locks[teacher_page_id] = threading.Lock()
    lock = _teacher_locks[teacher_page_id]
    lock.acquire()
    return lock
```

**Benefits**:
- Safe concurrent message handling per teacher
- Prevent duplicate Narrative creation
- Ensure correct time window calculations

### 4. Strategy Pattern (STT Engines)

**Purpose**: Support multiple STT engines with unified interface

**Example**: `core/audio/stt_translate.py`

```python
def decide_transcribe_model(file_path: str, engine: str = "gemini"):
    preprocessed = preprocess_for_stt(file_path)
    chunks = split_wav_to_chunks(preprocessed)

    if engine == "oai":
        return _transcribe_chunks_oai(chunks)
    elif engine == "gemini":
        return _transcribe_chunks_gemini(chunks)
    elif engine == "assemblyai":
        return transcribe_assemblyai_km_to_en(file_path)
    # ... etc
```

**Benefits**:
- Easy to add new STT providers
- Fallback options if one service fails
- Cost optimization (choose cheaper engines)

### 5. Hybrid Classification Pattern

**Purpose**: Combine vector search with LLM reasoning

**Example**: `impact_app/categorization/categorizer.py`

```python
def categorize(text: str) -> dict:
    # Step 1: Embedding-based voting
    embed_cat, embed_conf, evidence = _embed_vote(text)

    # Step 2: LLM refinement
    if CATEGORY_MODE == "hybrid":
        llm_cat, llm_conf, rationale = _llm_refine(text, evidence)
        return {
            "category": llm_cat,
            "confidence": max(embed_conf, llm_conf),
            "evidence": evidence,
            "rationale": rationale
        }
    else:
        return {"category": embed_cat, "confidence": embed_conf, ...}
```

**Benefits**:
- Fast retrieval (ChromaDB)
- Accurate reasoning (LLM)
- Explainable results (evidence + rationale)

---

## Database Schema

### Notion Database Relationships

```
┌─────────────┐
│  Schools DB │
└──────┬──────┘
       │
       │ Relation (1:N)
       │
       ▼
┌─────────────┐       ┌───────────────┐
│ Teachers DB │◄──────│ Narratives DB │
└──────┬──────┘       └───────┬───────┘
       │                      │
       │ Relation (1:N)       │ Relation (N:1)
       │                      │
       ▼                      ▼
┌────────────────────┐ ┌─────────────┐
│Staff Narratives DB │ │ Subjects DB │
└────────────────────┘ └─────────────┘
```

### Notion Property Types

| Notion Type | Python Type | Example |
|------------|-------------|---------|
| Title | str | "New Practice" |
| Rich Text | str | "This is a lesson about..." |
| Number | int / float | 12345, 0.85 |
| Select | str | "Math" |
| Checkbox | bool | True |
| Date | str (ISO8601) | "2026-01-03T10:30:00.000Z" |
| Relation | list[str] | ["page_id_1", "page_id_2"] |
| Files & Media | list[dict] | [{"name": "...", "external": {"url": "..."}}] |
| URL | str | "https://..." |

### ChromaDB Collection Schema

**Collection**: `categories`

| Field | Type | Description |
|-------|------|-------------|
| id | str | Auto-generated UUID |
| document | str | Category example text (from seed_categories.json) |
| metadata | dict | `{"category": "0:Teacher/Methods"}` |
| embedding | list[float] | OpenAI text-embedding-3-small (1536 dimensions) |

**Query Example**:
```python
results = collection.query(
    query_texts=["The teacher used visual aids"],
    n_results=5
)
# Returns top 5 most similar examples
```

---

## Next Steps

- Learn Narrative DB details: [04_narrative_db.md](04_narrative_db.md)
- Learn Impact DB details: [05_impact_db.md](05_impact_db.md)
- API reference: [06_api_reference.md](06_api_reference.md)
- Troubleshooting: [07_troubleshooting.md](07_troubleshooting.md)
