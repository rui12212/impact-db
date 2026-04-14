# Project Overview

## Table of Contents
- [Project Purpose](#project-purpose)
- [System Architecture](#system-architecture)
- [Two Core Services](#two-core-services)
- [Technology Stack](#technology-stack)
- [Documentation Structure](#documentation-structure)

---

## Project Purpose

This project is a system designed to collect and analyze teaching practices in Cambodian educational settings. It gathers daily lesson records and reflection comments through Telegram and stores them as structured data in Notion databases, supporting educational quality improvement and teacher development.

### Problems We Solve
- Teachers' daily lesson records are scattered and not systematically managed
- Transcribing and categorizing audio reflection comments is difficult manually
- No mechanism exists to analyze teaching practices by subject and category
- Need for a system that non-engineers can operate

---

## System Architecture

### Overall Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Telegram Bots                         │
│  ┌──────────────────────┐  ┌──────────────────────────┐    │
│  │   Narrative Bot      │  │     Impact Bot           │    │
│  │ (Lesson Recording)   │  │  (Audio Comment Analysis)│    │
│  └──────────┬───────────┘  └────────────┬─────────────┘    │
│             │                            │                   │
└─────────────┼────────────────────────────┼───────────────────┘
              │ Webhook                    │ Webhook
              │                            │
┌─────────────▼────────────────────────────▼───────────────────┐
│                     FastAPI Backend                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           project/main.py (Entry Point)              │   │
│  ├──────────────────────┬───────────────────────────────┤   │
│  │  narrative_app/      │     impact_app/               │   │
│  │  - Message aggreg.   │     - Audio preprocess        │   │
│  │  - Time window mgmt  │     - STT (Khmer)             │   │
│  │  - LLM summarization │     - Translation (English)   │   │
│  │  - Subject tagging   │     - Categorization          │   │
│  └──────────┬───────────┴────────────┬──────────────────┘   │
│             │                        │                       │
│  ┌──────────▼────────────────────────▼──────────────────┐   │
│  │                  core/                                │   │
│  │  - audio: Audio processing (preprocess, STT, trans.) │   │
│  │  - notion_client: Notion API client                  │   │
│  │  - telegram_helper: Telegram API helpers             │   │
│  │  - locks: Thread-safe processing management          │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                          │
                          │ Notion API / OpenAI API / Google Cloud APIs
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
│  ┌────────────┐  ┌──────────┐  ┌─────────────────────┐     │
│  │  Notion DB │  │ OpenAI   │  │  Google Cloud       │     │
│  │  - Schools │  │ - Whisper│  │  - Speech-to-Text   │     │
│  │  - Teachers│  │ - GPT-4  │  │  - Translate        │     │
│  │  -Narratives│ │ - Embed  │  │  - Gemini           │     │
│  │  - Impact  │  └──────────┘  └─────────────────────┘     │
│  └────────────┘                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  ChromaDB (Local)                                     │  │
│  │  - Vector store for category classification           │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Two Core Services

### 1. Narrative DB (Lesson Record Management)

**Purpose**: Collect teachers' daily teaching practices from Telegram, group them by time windows, and store in Notion

**Key Features**:
- Receive text/audio/image/video messages
- Automatic grouping by time windows (15 min ~ 18 hours)
- LLM-based summary generation (brief + detailed)
- Automatic subject tag classification (Khmer, Math, Science, etc.)
- Auto-sync to Staff Narrative DB

**Processing Flow**:
```
Receive Telegram Message
  ↓
Resolve School/Teacher (search existing or create new)
  ↓
Time Window Decision (15 min or 18 hours)
  ├─ Within window → Append to existing Narrative
  └─ Outside window → Close existing + generate summary → Create new Narrative
  ↓
Subject Tag Classification (OpenAI GPT-4)
  ↓
Sync to Staff Narrative DB
```

**Target Users**: Teachers recording daily lessons in group chats

---

### 2. Impact DB (Audio Comment Analysis)

**Purpose**: Transcribe, translate, and categorize teachers' audio comments during lesson observations and store in Notion

**Key Features**:
- Audio preprocessing (noise reduction, normalization, VAD trimming)
- Support for multiple STT engines (OpenAI Whisper, Google Gemini, AssemblyAI, Gladia, ElevenLabs)
- Automatic Khmer → English translation
- Automatic classification into 6 categories (ChromaDB + LLM hybrid)
- Storage in dedicated DBs per Training

**Processing Flow**:
```
Receive Telegram Audio Message
  ↓
Ensure Training Space (create dedicated DB per chat_id)
  ↓
Audio Download & Preprocessing
  ├─ Noise reduction
  ├─ Filtering (bandpass, EQ)
  ├─ Normalization & compression
  └─ VAD trimming
  ↓
Split into 30-second chunks (1.5s overlap)
  ↓
STT (Khmer) → Translation (English)
  ↓
Categorization
  ├─ ChromaDB embedding search (top 5)
  └─ LLM final decision (with confidence)
  ↓
Save to Notion DB (transcript + translation + category + rationale)
  ↓
Telegram Notification
```

**Target Users**: Educational trainers recording audio comments during lesson observations

---

## Technology Stack

### Backend
- **Python 3.9+**
- **FastAPI 0.115.0**: High-performance web framework
- **Uvicorn 0.30.6**: ASGI server

### External Services
| Service | Use Case | Main APIs |
|---------|----------|-----------|
| **Telegram Bot API** | Message reception, file download | Webhook, getFile, sendMessage |
| **Notion API** | Database management | databases.query, pages.create, blocks.append |
| **OpenAI API** | STT, translation, summarization, classification, embeddings | Whisper, GPT-4o-mini, text-embedding-3-small |
| **Google Cloud** | STT, translation | Speech-to-Text, Translate, Gemini |
| **ChromaDB** | Vector search | Local persistence |
| **AssemblyAI** | STT + simultaneous translation | (Optional) |
| **Gladia** | STT + translation | (Optional) |
| **ElevenLabs** | STT (Khmer) | (Optional) |

### Audio Processing
- **pydub**: Audio format conversion
- **soundfile**: WAV read/write
- **noisereduce**: Noise reduction
- **webrtcvad**: Voice Activity Detection
- **scipy/numpy**: Signal processing (filtering, EQ)

### Data Management
- **notion-client**: Notion API Python SDK
- **langchain-openai**: LangChain OpenAI integration
- **langchain-chroma**: ChromaDB integration
- **ulid-py**: Unique ID generation (timestamp-sortable)

---

## Documentation Structure

This documentation set is organized as follows:

1. **[01_overview.md](01_overview.md)** (This Document)
   - Project overview
   - System architecture
   - Technology stack

2. **[02_setup.md](02_setup.md)**
   - Development environment setup
   - Environment variable configuration
   - Notion database setup
   - Telegram Bot configuration

3. **[03_architecture.md](03_architecture.md)**
   - Directory structure
   - Module dependencies
   - Data flow details

4. **[04_narrative_db.md](04_narrative_db.md)**
   - Narrative DB detailed specs
   - Time window logic
   - LLM summarization
   - Subject tag classification

5. **[05_impact_db.md](05_impact_db.md)**
   - Impact DB detailed specs
   - Audio preprocessing pipeline
   - STT engine comparison
   - Categorization logic

6. **[06_api_reference.md](06_api_reference.md)**
   - FastAPI endpoints
   - Key function reference
   - Notion API usage patterns

7. **[07_troubleshooting.md](07_troubleshooting.md)**
   - Common issues and solutions
   - Log interpretation
   - Debugging techniques

---

## Design Philosophy

### 1. Operable by Non-Engineers
- Use familiar tools like Telegram as UI
- Visualize and manage data with Notion
- System continues even with errors

### 2. Reproducibility
- Docker support (docker-compose.yml)
- Configuration via environment variables
- Explicit package version specifications

### 3. Robust Error Handling
- Partial failures don't stop overall processing
- Detailed logging
- Telegram Webhooks always return 200 OK (prevent retries)

### 4. Extensibility
- Support for multiple STT engines (pluggable)
- Easy to add categories (update seed_categories.json only)
- Simple to add new Notion properties

### 5. Data Consistency
- Thread locks for concurrent access control
- ULID for unique ID generation
- UTC standardization to avoid timezone confusion

---

## Next Steps

- Setup development environment: See [02_setup.md](02_setup.md)
- Understand system architecture: See [03_architecture.md](03_architecture.md)
- Learn service details: See [04_narrative_db.md](04_narrative_db.md), [05_impact_db.md](05_impact_db.md)
