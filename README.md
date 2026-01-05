Narrative DB / Impact DB System

1. Overview

This repository contains two closely related backend services:

Narrative DB
Collects teachers’ daily practice narratives from Telegram and organizes them into structured Notion databases.

Impact DB
Processes voice-based impact comments from Telegram, performs audio preprocessing, speech-to-text (Khmer), translation (English), categorization, and stores results in Notion.

Both systems are designed with reproducibility, operational safety, and non-engineer usability in mind.


2. System Architecture (High Level)
Telegram
   |
   | (Webhook)
   v
FastAPI Backend
   |
   |-- Audio preprocessing (Impact DB only)
   |-- STT / Translation / Classification
   |
   v
Notion Databases

Key external services:
Telegram Bot API
Notion API
OpenAI API (Whisper / GPT)
Google Cloud APIs (Speech-to-Text, Translate)
Vector DB (Chroma, local)


3. Repository Structure
requirements.txt
README.md
.gitignore
.env
impact_db_env
project
├── narrative_app/        # Narrative DB logic
     ├── notion.repos     # The way of store data into dbs in Notion
     ├── classification.py # Adding subject tag using Open AI
     ├── grouping.py      # Logic of setting time-window
     ├── service_staff.py # Logic of synchronize Narrative DB to Staff_Narrative DB
     ├── service.py       # Main logic of processing audio/text/media -> summary -> Notion
     ├── summarization.py # Logic of summarizing of the detailed contents of each narrative
├── impact_app/           # Impact DB logic
│    ├── categorization/  # Audio preprocessing & chunking
│    └── notion/          # Logic for the way of storing the data to dbs on Notion
│    └── service.py       # Main logic of processing STT->Translate->Categorize->Notion DB
├── core/
│   ├── audio/            # Audio preprocessing & chunking
│   ├── config.py         # summary of API from env
│   ├── locks.py          # One-time-One_post logic for protecting post on telegram
│   └── notion_client.py  # Define Notion client
│   └── telegram_helper.py  # Define basic connection to telegram
├── config/
│   └── config.py         # Environment variable validation
├── docker-compose.yml    # (optional, recommended)
└── README.md


4. Prerequisites
Required Accounts

Telegram (BotFather access)
Notion (Integration token)
OpenAI
Google Cloud Platform
Runtime
Python 3.9+
ffmpeg (required for audio processing)
Recommended:
Docker + Docker Compose (for reproducibility)


5. Environment Variables
OPENAI_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=
PUBLIC_BASE_URL=
NARRATIVE_TELEGRAM_BOT_TOKEN=
NARRATIVE_TELEGRAM_SECRET_TOKEN=
IMPACT_TELEGRAM_BOT_TOKEN=
IMPACT_TELEGRAM_SECRET_TOKEN=
NOTION_API_KEY=

NOTION_ROOT_PAGE_ID=
NOTION_SCHOOLS_DB_ID=
NOTION_TEACHERS_DB_ID=
NOTION_NARRATIVES_DB_ID=
NOTION_SUBJECTS_DB_ID=
NOTION_STAFF_NARRATIVE_DB_ID=
NOTION_IMPACT_TRAINING_DB_ID=
⚠️ Never commit .env files to Git.
In production environments, use a secrets manager.


6. Notion Database Setup
Narrative DB (Required)
You must create the following databases with exact property names:
Schools DB
 -- Name (Title)
Teachers DB
 -- Name (Title)
 -- School (Relation → Schools)
 -- Telegram User ID (Rich text)
Narratives DB
 -- Name (Title)
 -- School (Relation)
 -- Teacher (Relation)
 -- Raw Text (Rich text)
 -- Subject Tag (Select)
 -- Subject (Relation)
 -- Media (Files)
 -- Date (Date)
 -- Is Closed (Checkbox)
*Narrative summaries are written as page children blocks:
 -- Summary
 -- Detailed
 -- Media (image / video blocks)
Subjects DB
 -- Name (Title)
Staff Narrative DB
 -- School_name (Relation)
 -- Teacher_name (Relation)
 -- Subject Tag (Relation)
 -- Last Practice At (Date)
 -- Latest Narrative (Relation)

Impact DB (Required)
All_Training_Impact DB
 -- Name (Title) → Telegram group name
 * Property of child DB of the All_Training_Impact DB
 --- Name (Title)
 --- Date (Date)
 --- STT_Km (Rich text)
 --- Translated_En (Rich text)
 --- Category (Select)
 --- CategoryConfidence (Number)
 --- AudioURL (URL)
 --- ChatID (Number)
 --- MessageID (Number)
 --- ExternalID (Rich text)


7. Running the Application
A: Docker (Recommended)
docker compose up --build


8. Telegram Webhook Setup
https://api.telegram.org/bot<token>/setWebhook


9. Processing Flow
Narrative DB
 -- Receive Telegram update
 -- Resolve School (by chat title)
 -- Resolve Teacher (by user ID)
 -- Append message to open Narrative
 -- Close Narrative when time window expires
 -- Generate Summary / Detailed text
 -- Update Staff Narrative DB
Impact DB
 -- Receive voice message
 -- Download audio via Telegram API
 -- Audio preprocessing (normalize, chunking)
 -- STT (Khmer)
 -- Translation (English)
 -- Categorization (embedding + LLM)
 -- Save to Notion child DB
 -- Notify Telegram (optional)


10. Documentation
For detailed documentation, see the docs/ folder:
 -- docs/01_overview.md - Project overview and architecture
 -- docs/02_setup.md - Setup and configuration guide
 -- docs/03_architecture.md - System architecture details
 -- docs/04_narrative_db.md - Narrative DB implementation
 -- docs/05_impact_db.md - Impact DB implementation
 -- docs/06_api_reference.md - API and function reference
 -- docs/07_troubleshooting.md - Troubleshooting guide
 -- docs/08_test_environment_sharing_design.md - Test environment sharing (AWS Lightsail)