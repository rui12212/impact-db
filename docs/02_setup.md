# Setup Guide

## Table of Contents
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Notion Database Configuration](#notion-database-configuration)
- [Telegram Bot Setup](#telegram-bot-setup)
- [Running the Application](#running-the-application)
- [Webhook Configuration](#webhook-configuration)

---

## Prerequisites

### Required Accounts
1. **Telegram** - BotFather access to create bots
2. **Notion** - Workspace with integration token
3. **OpenAI** - API key for GPT and Whisper
4. **Google Cloud Platform** - Service account with Speech-to-Text and Translate APIs enabled

### Optional Services
- **AssemblyAI** - For alternative STT engine
- **Gladia** - For alternative STT engine
- **ElevenLabs** - For alternative Khmer STT
- **Google Gemini** - For alternative STT/translation

### System Requirements
- **Python 3.9+**
- **ffmpeg** (required for audio processing)
  ```bash
  # macOS
  brew install ffmpeg

  # Ubuntu/Debian
  sudo apt-get install ffmpeg

  # Windows
  # Download from https://ffmpeg.org/download.html
  ```
- **Docker + Docker Compose** (recommended for deployment)

---

## Environment Setup

### 1. Clone Repository
```bash
git clone <repository-url>
cd impact_db
```

### 2. Create Virtual Environment
```bash
python -m venv impact_db_env
source impact_db_env/bin/activate  # macOS/Linux
# or
impact_db_env\Scripts\activate     # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

**requirements.txt**:
```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-dotenv==1.0.1
requests==2.32.3
openai==1.47.0
gspread==6.1.2
google-auth==2.33.0
google-cloud-translate==3.15.5
ulid-py==1.1.0
notion-client
langchain-openai
langchain-chroma
soundfile
pydub
webrtcvad
noisereduce
scipy
numpy
elevenlabs
google-genai
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# ============================================
# Core APIs
# ============================================
OPENAI_API_KEY=sk-proj-...
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini

# ============================================
# Google Cloud
# ============================================
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json

# ============================================
# Public URL (for Telegram Webhook)
# ============================================
PUBLIC_BASE_URL=https://your-domain.com
# For local development with Cloudflare Tunnel:
# PUBLIC_BASE_URL=https://xxxxx.trycloudflare.com

# ============================================
# Telegram Bots
# ============================================
NARRATIVE_TELEGRAM_BOT_TOKEN=8545505468:AAE-...
NARRATIVE_TELEGRAM_SECRET_TOKEN=<random-secret-token>

IMPACT_TELEGRAM_BOT_TOKEN=7516377217:AAG...
IMPACT_TELEGRAM_SECRET_TOKEN=<random-secret-token>

# ============================================
# Notion
# ============================================
NOTION_API_KEY=ntn_...
NOTION_ROOT_PAGE_ID=<page-id>
NOTION_SCHOOLS_DB_ID=<db-id>
NOTION_TEACHERS_DB_ID=<db-id>
NOTION_NARRATIVES_DB_ID=<db-id>
NOTION_SUBJECTS_DB_ID=<db-id>
NOTION_STAFF_NARRATIVES_DB_ID=<db-id>

# ============================================
# Impact DB Settings
# ============================================
CATEGORY_MODE=hybrid  # "embed" or "hybrid"
CHROMA_DIR=.chroma_categories
CATEGORY_SEED_PATH=seed_categories.json

# ============================================
# Narrative Window Settings
# ============================================
NARRATIVE_WINDOW_MINUTES=1080  # 18 hours (production)
# NARRATIVE_WINDOW_MINUTES=15  # For testing

# ============================================
# Optional STT Services
# ============================================
ASSEMBLYAI_API_KEY=bc069caf...
GLADIA_API_KEY=2237662b-...
ELEVENLABS_API_KEY=sk_4c4004c9...
GEMINI_API_KEY=AIzaSyBJTasSL...
```

**Security Notes**:
- **Never commit `.env` to Git** (already in `.gitignore`)
- Generate secret tokens: `openssl rand -hex 32`
- In production, use a secrets manager (AWS Secrets Manager, Google Secret Manager, etc.)

---

## Notion Database Configuration

### Required Databases

You need to create the following databases in Notion with **exact property names**:

#### 1. Schools DB

| Property Name | Type | Description |
|--------------|------|-------------|
| Name | Title | School name (from Telegram chat title) |
| Telegram Chat ID | Number | Telegram chat ID |

#### 2. Teachers DB

| Property Name | Type | Description |
|--------------|------|-------------|
| Name | Title | Teacher name (first_name + last_name) |
| School | Relation → Schools | School relation |
| Telegram User ID | Number | Telegram user ID |
| Telegram Username | Rich Text | @username |

#### 3. Narratives DB

| Property Name | Type | Description |
|--------------|------|-------------|
| Title | Title | Default: "New Practice" |
| Teacher | Relation → Teachers | Teacher relation |
| School | Relation → Schools | School relation |
| Raw Text | Rich Text | Raw message text (hidden, stored in child blocks) |
| Subject Tag | Select | Options: "Khmer", "Math", "Science", "PE", "IT", "Reginal Lifeskill Program", "None" |
| Subject | Relation → Subjects | Subject relation |
| Media | Files & Media | Image/video URLs |
| Date | Date | start=opening time, end=closing time |
| Is Closed | Checkbox | Whether time window is closed |

**Child Block Structure**:
- Heading 2: "Raw Text" → Paragraph blocks
- Heading 2: "Summary" (added on close) → Paragraph
- Heading 2: "Detailed Class Content" → Paragraph
- Heading 2: "Media" → Image/Video blocks

#### 4. Subjects DB

| Property Name | Type | Description |
|--------------|------|-------------|
| Name | Title | Subject name |

**Pre-populate** with: Khmer, Math, Science, PE, IT, Reginal Lifeskill Program, None

#### 5. Staff Narratives DB

| Property Name | Type | Description |
|--------------|------|-------------|
| Name | Title | Default: "Staff Narrative" |
| School_name | Relation → Schools | School relation |
| Teacher_name | Relation → Teachers | Teacher relation |
| Subject Tag | Relation → Subjects | Multiple subjects allowed |
| Last Practice At | Date | Last practice date |
| Latest Narrative | Relation → Narratives | Latest narrative |

#### 6. Training Impact DBs (Auto-generated)

**Parent Page**: Create a root page under `NOTION_ROOT_PAGE_ID`

**Child DBs** (auto-created per training):

| Property Name | Type | Description |
|--------------|------|-------------|
| Name | Title | Filename or date_chat_id |
| Date | Date | Processing timestamp |
| STT_Km | Rich Text | Khmer transcript |
| Translated_En | Rich Text | English translation |
| Category | Select | Options: "0:Teacher/Methods", "1:Mass Students", "2a:Individual Character", "2b:Individual Evaluation", "2c:Individual Verification", "2d:Learning of how Student Learn", "fact:Mentioning facts" |
| CategoryConfidence | Number | Confidence score |
| AudioURL | URL | Telegram file URL |
| ChatID | Number | Telegram chat ID |
| MessageID | Number | Telegram message ID |
| ExternalID | Rich Text | Format: "tg:{update_id}" |

### Notion Integration Setup

1. Go to https://www.notion.so/my-integrations
2. Create a new integration
3. Copy the **Internal Integration Token** → `NOTION_API_KEY`
4. Share all databases with the integration:
   - Open each database
   - Click "⋯" → "Add connections" → Select your integration

---

## Telegram Bot Setup

### Create Bots

1. Open Telegram and search for **@BotFather**
2. Create Narrative Bot:
   ```
   /newbot
   Name: Narrative Bot (or your choice)
   Username: your_narrative_bot
   ```
   Copy the token → `NARRATIVE_TELEGRAM_BOT_TOKEN`

3. Create Impact Bot:
   ```
   /newbot
   Name: Impact Bot (or your choice)
   Username: your_impact_bot
   ```
   Copy the token → `IMPACT_TELEGRAM_BOT_TOKEN`

### Bot Permissions

For both bots, configure:
```
/setprivacy → Disable (to read group messages)
/setjoingroups → Enable
```

### Add Bots to Groups

- Add **Narrative Bot** to teacher group chats
- Add **Impact Bot** to trainer observation chats
- Make them admins (optional, but recommended for reliability)

---

## Running the Application

### Option 1: Local Development

```bash
# Activate virtual environment
source impact_db_env/bin/activate

# Run FastAPI server
cd project
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**For local testing with Telegram Webhook**, use Cloudflare Tunnel:
```bash
# Install cloudflared
brew install cloudflare/cloudflare/cloudflared

# Start tunnel
cloudflared tunnel --url http://localhost:8000
# Copy the https://xxxxx.trycloudflare.com URL → PUBLIC_BASE_URL
```

### Option 2: Docker (Recommended for Production)

Create `docker-compose.yml` in project root:

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./project:/app/project
      - ./.env:/app/.env
      - ./project/.chroma_categories:/app/project/.chroma_categories
      - ./project/.runtime:/app/project/.runtime
    environment:
      - PYTHONUNBUFFERED=1
    command: uvicorn project.main:app --host 0.0.0.0 --port 8000
```

Create `Dockerfile`:

```dockerfile
FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY project/ ./project/
COPY .env .

EXPOSE 8000

CMD ["uvicorn", "project.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Run:
```bash
docker compose up --build
```

---

## Webhook Configuration

### Set Telegram Webhooks

After deploying the app, configure webhooks:

#### Narrative Bot Webhook
```bash
curl -X POST "https://api.telegram.org/bot${NARRATIVE_TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"${PUBLIC_BASE_URL}/telegram/narrative/webhook\",
    \"secret_token\": \"${NARRATIVE_TELEGRAM_SECRET_TOKEN}\"
  }"
```

#### Impact Bot Webhook
```bash
curl -X POST "https://api.telegram.org/bot${IMPACT_TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"${PUBLIC_BASE_URL}/telegram/impact/webhook\",
    \"secret_token\": \"${IMPACT_TELEGRAM_SECRET_TOKEN}\"
  }"
```

### Verify Webhook Status
```bash
curl "https://api.telegram.org/bot${NARRATIVE_TELEGRAM_BOT_TOKEN}/getWebhookInfo"
curl "https://api.telegram.org/bot${IMPACT_TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected response:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com/telegram/narrative/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

## ChromaDB Initialization

The system auto-initializes ChromaDB on first run using `seed_categories.json`.

Create `project/seed_categories.json`:

```json
{
  "0:Teacher/Methods": [
    "The teacher used group discussion to engage students.",
    "Teacher explained the concept with visual aids."
  ],
  "1:Mass Students": [
    "All students participated actively in the activity.",
    "The class showed great enthusiasm."
  ],
  "2a:Individual Character": [
    "Sokha is very creative in problem-solving.",
    "Dara shows leadership qualities."
  ],
  "2b:Individual Evaluation": [
    "Channthy scored 85% on the math quiz.",
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

---

## Health Check

Verify the app is running:

```bash
curl http://localhost:8000/healthz
```

Expected response:
```json
{
  "ok": true,
  "time": "2026-01-03T10:30:00Z"
}
```

---

## Next Steps

- Understand system architecture: [03_architecture.md](03_architecture.md)
- Learn Narrative DB details: [04_narrative_db.md](04_narrative_db.md)
- Learn Impact DB details: [05_impact_db.md](05_impact_db.md)
- API reference: [06_api_reference.md](06_api_reference.md)
- Troubleshooting: [07_troubleshooting.md](07_troubleshooting.md)
