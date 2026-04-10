# Narrative DB - Detailed Documentation

## Table of Contents
- [Overview](#overview)
- [Processing Flow](#processing-flow)
- [Time Window Logic](#time-window-logic)
- [LLM Summarization](#llm-summarization)
- [Subject Tag Classification](#subject-tag-classification)
- [Staff Narrative Sync](#staff-narrative-sync)
- [Code Reference](#code-reference)

---

## Overview

**Narrative DB** collects teachers' daily teaching practices from Telegram group chats and organizes them into structured Notion databases. Messages are automatically grouped by time windows, summarized using LLMs, and tagged with subject classifications.

### Key Features
- **Auto-grouping**: Messages within a configurable time window (15 min - 18 hours) are grouped into a single Narrative
- **Multi-format support**: Text, voice, images, videos
- **Smart translation**: Khmer → English automatic translation
- **LLM summarization**: Generate brief and detailed summaries when a Narrative closes
- **Subject classification**: Automatically tag with subject (Math, Science, etc.)
- **Staff tracking**: Sync to Staff Narrative DB for management overview

### Supported Message Types
| Type | Processing | Output |
|------|------------|--------|
| Text | Khmer → English translation | English text |
| Voice | STT (Khmer) → Translation (English) | English transcript |
| Photo | File ID → URL | Image block in Notion |
| Video | File ID → URL | Video block in Notion |
| Document (image/video) | Auto-detect by MIME type or extension | Image/Video block |

---

## Processing Flow

### High-Level Flow

```
1. Telegram Webhook → FastAPI
2. Extract user, chat, timestamp, content
3. Resolve School (by chat_id)
4. Resolve Teacher (by user_id)
5. Acquire thread lock for teacher
6. Decide Narrative:
   ├─ No open Narrative → Create new
   ├─ Within window → Append to existing
   └─ Outside window → Close old + Create new
7. Append media (if any)
8. Release lock
9. Return 200 OK to Telegram
```

### Detailed Step-by-Step

#### Step 1: Message Reception
```python
# project/main.py
@app.post('/telegram/narrative/webhook')
async def narrative_webhook(request: Request, background: BackgroundTasks):
    # Validate secret token
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != NARRATIVE_TELEGRAM_SECRET_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    update = await request.json()
    background.add_task(handle_telegram_update, update)
    return JSONResponse({"ok": True})
```

#### Step 2: Extract Metadata
```python
# narrative_app/service.py:208
message = update.get("message") or update.get("edited_message")
from_user = message["from"]  # {id, first_name, last_name, username}
chat = message["chat"]        # {id, title, type}
date_ts = message.get("date") # Unix timestamp (UTC)
message_dt = datetime.fromtimestamp(date_ts, tz=timezone.utc)
```

#### Step 3: Resolve School
```python
# narrative_app/service.py:69
def resolve_school(chat: TelegramChatInfo) -> str:
    school_page_id = get_or_create_school_by_chat(
        chat_id=chat.chat_id,
        chat_title=chat.title
    )
    return school_page_id

# narrative_app/notion_repos/notion_repos.py
def get_or_create_school_by_chat(chat_id: int, chat_title: str) -> str:
    # Query Notion Schools DB
    results = notion.databases.query(
        database_id=NOTION_SCHOOLS_DB_ID,
        filter={
            "property": "Telegram Chat ID",
            "number": {"equals": chat_id}
        }
    )

    if results["results"]:
        return results["results"][0]["id"]

    # Create new school
    page = notion.pages.create(
        parent={"database_id": NOTION_SCHOOLS_DB_ID},
        properties={
            "Name": {"title": [{"text": {"content": chat_title}}]},
            "Telegram Chat ID": {"number": chat_id}
        }
    )
    return page["id"]
```

#### Step 4: Resolve Teacher
```python
# narrative_app/service.py:78
def resolve_teacher(user: TelegramUserInfo, school_page_id: str) -> str:
    display_name = build_display_name(user)  # "FirstLast" or "@username" or "User 12345"
    teacher_page_id = get_or_create_teacher_by_telegram(
        telegram_user_id=user.user_id,
        name=display_name,
        username=user.first_name,
        school_page_id=school_page_id,
    )
    return teacher_page_id
```

#### Step 5: Process Content

**Text Message**:
```python
# narrative_app/service.py:239
text = message.get("text")
if text:
    translated_text = oai_translate_km_to_en(text)
    text = translated_text[0]
```

**Voice Message**:
```python
# narrative_app/service.py:243
voice = pick_audio_from_message(message)
if voice and "file_id" in voice:
    file_url = tg_get_file_url(file_id, narrative_bot_token)
    # Download to temp file
    # ...
    stt_text_km, stt_conf = oai_transcribe(src)
    translate_en_text, trans_src = oai_translate_km_to_en(stt_text_km)
    text = translate_en_text
```

**Photo/Video**:
```python
# narrative_app/service.py:265
photos = message.get("photo") or []
if photos:
    largest_photo = photos[-1]
    if "file_id" in largest_photo:
        media_files.append(("photo", largest_photo["file_id"]))

video = message.get("video")
if video and "file_id" in video:
    media_files.append(("video", video["file_id"]))
```

#### Step 6: Decide Narrative (Thread-Safe)
```python
# narrative_app/service.py:318
teacher_lock = get_teacher_lock(teacher_id)

with teacher_lock:
    result = decide_and_get_narrative(
        teacher_page_id=teacher_id,
        school_page_id=school_id,
        message_dt=message_dt,
        text=text,
    )
```

**Three Scenarios**:

1. **No Open Narrative**:
```python
# narrative_app/service.py:127
if open_narrative is None:
    narrative_page_id = create_narrative(
        title="New Practice",
        teacher_page_id=teacher_page_id,
        school_page_id=school_page_id,
        start_timestamp_iso=to_iso(message_dt),
        raw_text=text,
    )
    return NarrativeDecisionResult(
        narrative_page_id=narrative_page_id,
        is_new=True,
        started_at=message_dt,
    )
```

2. **Within Time Window**:
```python
# narrative_app/service.py:155
if is_within_window(first_ts, message_dt):
    narrative_page_id = open_narrative["id"]
    append_and_update_narrative_children(
        narrative_page_id=narrative_page_id,
        additional_text=text,
    )
    return NarrativeDecisionResult(
        narrative_page_id=narrative_page_id,
        is_new=False,
        started_at=first_ts,
    )
```

3. **Outside Time Window**:
```python
# narrative_app/service.py:170
narrative_page_id_old = open_narrative["id"]

# Close old Narrative
close_narrative(
    narrative_page_id=narrative_page_id_old,
    end_timestamp_iso=to_iso(message_dt),
)

# Sync to Staff Narrative DB
sync_staff_narrative_from_narrative(narrative_page_id_old)

# Add subject tag
enrich_narrative_with_tags(narrative_page_id_old)

# Create new Narrative
narrative_page_id_new = create_narrative(...)
```

#### Step 7: Append Media
```python
# narrative_app/service.py:337
for kind, file_id in media_files:
    try:
        url = tg_get_file_url(file_id, narrative_bot_token)
        name = "Photo" if kind == "photo" else "Video"
        append_media_to_narrative(
            narrative_page_id=narrative_page_id,
            media_url=url,
            name=name,
        )
    except Exception as e:
        logger.exception("Failed to append media: %s", e)
```

---

## Time Window Logic

### Configuration

```bash
# .env
NARRATIVE_WINDOW_MINUTES=1080  # 18 hours (production)
# NARRATIVE_WINDOW_MINUTES=15  # 15 minutes (testing)
```

### Implementation

**File**: `narrative_app/grouping.py`

```python
from datetime import timedelta
from core.config import NARRATIVE_WINDOW_MINUTES

def is_within_window(first_timestamp: datetime, new_timestamp: datetime) -> bool:
    """
    Check if new_timestamp is within NARRATIVE_WINDOW_MINUTES of first_timestamp

    Args:
        first_timestamp: When the Narrative started (Date.start)
        new_timestamp: Current message timestamp

    Returns:
        True if within window, False otherwise
    """
    window = timedelta(minutes=NARRATIVE_WINDOW_MINUTES)
    return (new_timestamp - first_timestamp) <= window
```

### Use Cases

| Window Size | Use Case | Example |
|------------|----------|---------|
| 15 minutes | Testing, rapid iteration | Quick demo or debugging |
| 1 hour | Short activities | Single class period |
| 3 hours | Half-day activities | Morning session |
| 18 hours (1080 min) | **Production default** | Teacher's daily practice (across multiple lessons) |

### Timezone Handling

All timestamps are **UTC**:

```python
# narrative_app/grouping.py:4
def parse_iso(ts: str) -> datetime:
    """Parse ISO8601 string to datetime (UTC)"""
    if ts.endswith("Z"):
        ts = ts[:-1]
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)

def to_iso(dt: datetime) -> str:
    """Convert datetime to ISO8601 string with 'Z' suffix"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
```

**Example**:
```
First message: 2026-01-03T08:00:00Z
Window: 18 hours
Deadline: 2026-01-04T02:00:00Z

Message at 2026-01-03T20:00:00Z → Within window (appends)
Message at 2026-01-04T03:00:00Z → Outside window (closes old, creates new)
```

---

## LLM Summarization

When a Narrative closes (time window expires), two summaries are generated:

### 1. Brief Summary

**Function**: `generate_summary(raw_text: str) -> str`
**File**: `narrative_app/summarization.py:36`

**Model**: `gpt-4.1-mini`
**Temperature**: Default (not specified, likely 0.7)

**Prompt**:
```
You are given a narrative written by a teacher about a class or educational activity.

[NARRATIVE]
{raw_text}

Task:
- Summarize the overall class or activity in a concise way.
- Focus on:
  - What the teacher tried to do (aim / intention)
  - What kind of activity was conducted
  - How students responded in general
- Write in 3-6 sentences.
```

**Output**: 3-6 sentence summary focusing on teacher's intention, activity type, and student response

**Example**:
```
The teacher introduced fractions using pizza slices as visual aids.
Students were divided into groups to practice dividing pizzas equally.
Most students understood the concept quickly and participated actively.
Some struggled with denominators, so the teacher provided extra examples.
Overall, the hands-on approach helped students grasp the abstract concept.
```

### 2. Detailed Content

**Function**: `generate_detailed_content(raw_text: str) -> str`
**File**: `narrative_app/summarization.py:61`

**Model**: `gpt-4.1-mini`
**Temperature**: Default

**Prompt**:
```
You are given a narrative written by a teacher about a class or educational activity.

[NARRATIVE]
{raw_text}

Task:
- Extract the concrete flow and content of the class in more detail
- Organize the answer in bullet points or short paragraphs.
- Include, if possible:
  - Preparation / Introduction
  - Main activity steps
  - How students reacted (with some concrete examples)
  - How the class was wrapped up
- Do NOT repeat a short summary only. Go into more detail so that
  another teacher could imagine reusing this practice.
```

**Output**: Detailed breakdown in bullets/paragraphs with concrete steps and examples

**Example**:
```
Preparation:
- Prepared pizza slice diagrams on cardboard
- Divided class into 5 groups of 6 students each

Introduction (5 minutes):
- Asked "What does half of a pizza mean?"
- Students shared their thoughts

Main Activity (20 minutes):
- Groups received pizza diagrams and scissors
- Task: Cut pizzas into equal parts (halves, thirds, quarters)
- Sokha's group quickly understood halves but struggled with thirds
- Dara helped her group by drawing lines first

Student Reactions:
- Most groups enthusiastically cut and compared pieces
- Some confusion about denominator meaning
- Channthy asked "Why is 1/3 bigger than 1/4?" → good question for discussion

Wrap-up (10 minutes):
- Each group presented their results
- Teacher clarified denominator = number of equal parts
- Homework: Draw 3 pizzas divided into 2, 3, and 4 parts
```

### Storage in Notion

Both summaries are appended as **child blocks** to the Narrative page:

```python
# Stored in page children, NOT properties
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
        "heading_2": {"rich_text": [{"text": {"content": "Detailed Class Content"}}]}
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

---

## Subject Tag Classification

### Available Tags

```python
# narrative_app/classification.py:7
SUBJECT_TAGS = [
    "Khmer",
    "Math",
    "Science",
    "PE",
    "IT",
    "Reginal Lifeskill Program",
    "None",
]
```

### Classification Process

**Function**: `classify_subject(raw_text: str) -> Optional[str]`
**File**: `narrative_app/classification.py:21`

**Model**: `gpt-4.1-mini`
**Output Format**: `{"type": "json_object"}`

**System Prompt**:
```
You are a classifier for school lesson narratives.
From the given text, choose appropriate subject tags from the provided lists.
Only use tags from the lists. Return a JSON object with fields "subject_tags" with string.
```

**User Prompt**:
```
[TEXT]
{raw_text}

[AVAILABLE SUBJECT TAGS]
Khmer,Math,Science,PE,IT,Reginal Lifeskill Program,None

Rules:
- Only use tags from the available lists.
- subject_tags: choose only ONE tag that fit best
- If unsure, set subject_tags to "" (empty string).

Return JSON like:
{
  "subject_tags": "Math"
}
```

### Response Handling

```python
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[...],
    response_format={"type": "json_object"},
)

content = response.choices[0].message.content
subject_json_data = json.loads(content)
subject_tag = subject_json_data.get("subject_tags", "")

# Validation
if subject_tag not in SUBJECT_TAGS:
    logger.warning("Unknown subject tag from LLM: %s", subject_tag)
    return None

return subject_tag
```

### Notion Update

```python
# narrative_app/service.py:189
enrich_narrative_with_tags(narrative_page_id_old)

# Inside enrich_narrative_with_tags():
raw_text = get_raw_text_from_narrative(narrative_page_id)
subject_tag = classify_subject(raw_text)

update_narrative_tags(
    narrative_page_id=narrative_page_id,
    subject_tag=subject_tag,
)
```

**Notion Property Update**:
```python
notion.pages.update(
    page_id=narrative_page_id,
    properties={
        "Subject Tag": {"select": {"name": subject_tag}}
    }
)
```

---

## Staff Narrative Sync

### Purpose

The **Staff Narratives DB** provides a management overview of each teacher's latest practice per subject.

### Sync Trigger

When a Narrative closes:

```python
# narrative_app/service.py:180
try:
    sync_staff_narrative_from_narrative(narrative_page_id_old)
except Exception as e:
    logger.exception("failed to sync staff narrative: %s", e)
```

### Sync Logic

**Function**: `sync_staff_narrative_from_narrative(narrative_page_id: str)`
**File**: `narrative_app/service_staff_narrative.py`

**Steps**:

1. **Fetch Narrative details**:
```python
narrative_page = notion.pages.retrieve(page_id=narrative_page_id)
props = narrative_page["properties"]

teacher_relation = props.get("Teacher", {}).get("relation", [])
school_relation = props.get("School", {}).get("relation", [])
subject_tag = props.get("Subject Tag", {}).get("select", {}).get("name")
date_prop = props.get("Date", {}).get("date", {})
```

2. **Resolve Subject IDs**:
```python
subject_page_ids = resolve_subject_ids([subject_tag])
# Queries Subjects DB by name, creates if not exists
```

3. **Query Staff Narrative DB**:
```python
# Find existing Staff Narrative for this teacher
results = notion.databases.query(
    database_id=NOTION_STAFF_NARRATIVES_DB_ID,
    filter={
        "property": "Teacher_name",
        "relation": {"contains": teacher_page_id}
    }
)
```

4. **Update or Create**:
```python
if results["results"]:
    # Update existing
    staff_page_id = results["results"][0]["id"]
    notion.pages.update(
        page_id=staff_page_id,
        properties={
            "Subject Tag": {"relation": subject_page_ids},
            "Last Practice At": {"date": date_prop},
            "Latest Narrative": {"relation": [narrative_page_id]}
        }
    )
else:
    # Create new
    notion.pages.create(
        parent={"database_id": NOTION_STAFF_NARRATIVES_DB_ID},
        properties={
            "Name": {"title": [{"text": {"content": "Staff Narrative"}}]},
            "School_name": {"relation": school_relation},
            "Teacher_name": {"relation": teacher_relation},
            "Subject Tag": {"relation": subject_page_ids},
            "Last Practice At": {"date": date_prop},
            "Latest Narrative": {"relation": [narrative_page_id]}
        }
    )
```

### Staff Narrative Schema

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Always "Staff Narrative" |
| School_name | Relation → Schools | School relation |
| Teacher_name | Relation → Teachers | Teacher relation |
| Subject Tag | Relation → Subjects | Can have multiple subjects |
| Last Practice At | Date | Date of latest practice |
| Latest Narrative | Relation → Narratives | Link to most recent Narrative |

---

## Code Reference

### Key Files

| File | Purpose | Lines of Code |
|------|---------|---------------|
| `narrative_app/service.py` | Main service logic | 364 |
| `narrative_app/grouping.py` | Time window logic | 24 |
| `narrative_app/classification.py` | Subject tagging | 90 |
| `narrative_app/summarization.py` | LLM summarization | 87 |
| `narrative_app/service_staff_narrative.py` | Staff DB sync | ~100 |
| `narrative_app/notion_repos/notion_repos.py` | Notion CRUD operations | ~500 |

### Key Functions

#### `handle_telegram_update(update: dict) -> None`
**File**: `narrative_app/service.py:208`

Main entry point for Telegram webhook. Orchestrates entire processing flow.

**Error Handling**:
- All exceptions caught and logged
- Always returns (Telegram receives 200 OK)

---

#### `decide_and_get_narrative(teacher_page_id, school_page_id, message_dt, text) -> NarrativeDecisionResult`
**File**: `narrative_app/service.py:110`

Core logic for Narrative grouping.

**Returns**:
```python
@dataclass
class NarrativeDecisionResult:
    narrative_page_id: str
    is_new: bool
    started_at: datetime
```

---

#### `close_narrative(narrative_page_id: str, end_timestamp_iso: str)`
**File**: `narrative_app/notion_repos/notion_repos.py`

Steps:
1. Fetch raw text from child blocks
2. Generate summary and detailed content
3. Extract media items
4. Append summary, detailed, and media blocks
5. Update properties: `Is Closed = True`, `Date.end = end_timestamp_iso`

---

## Next Steps

- Learn Impact DB details: [05_impact_db.md](05_impact_db.md)
- API reference: [06_api_reference.md](06_api_reference.md)
- Troubleshooting: [07_troubleshooting.md](07_troubleshooting.md)
