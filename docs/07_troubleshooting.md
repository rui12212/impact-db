# Troubleshooting Guide

## Table of Contents
- [Common Issues](#common-issues)
- [Debugging Techniques](#debugging-techniques)
- [Log Analysis](#log-analysis)
- [Notion API Issues](#notion-api-issues)
- [Telegram Bot Issues](#telegram-bot-issues)
- [Audio Processing Issues](#audio-processing-issues)
- [Performance Optimization](#performance-optimization)

---

## Common Issues

### 1. Telegram Bot Not Responding

**Symptoms**:
- Messages sent to Telegram group, but no response
- No errors in logs

**Possible Causes & Solutions**:

#### A. Webhook Not Set
```bash
# Check webhook status
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

**Expected**:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com/telegram/narrative/webhook",
    "pending_update_count": 0
  }
}
```

**If `url` is empty**, set webhook:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/telegram/narrative/webhook",
    "secret_token": "<SECRET_TOKEN>"
  }'
```

#### B. Wrong Secret Token
Check that `.env` has correct secret token:
```bash
# In .env
NARRATIVE_TELEGRAM_SECRET_TOKEN=<same-token-used-in-setWebhook>
```

#### C. Server Not Accessible
Test if server is reachable:
```bash
curl http://localhost:8000/healthz
# Should return: {"ok": true, "time": "..."}
```

If using Cloudflare Tunnel, ensure tunnel is running:
```bash
cloudflared tunnel --url http://localhost:8000
```

#### D. Bot Not Added to Group
- Ensure bot is added as member to Telegram group
- Make bot admin (recommended for reliability)
- Check with `/setprivacy` → Disable (allows bot to read all messages)

---

### 2. Notion "Unauthorized" Error

**Error Log**:
```
notion_client.errors.APIResponseError: Unauthorized
```

**Causes & Solutions**:

#### A. Invalid API Key
Check `.env`:
```bash
NOTION_API_KEY=ntn_...  # Must start with "ntn_" or "secret_"
```

Test API key:
```bash
curl https://api.notion.com/v1/users/me \
  -H "Authorization: Bearer ${NOTION_API_KEY}" \
  -H "Notion-Version: 2022-06-28"
```

#### B. Database Not Shared with Integration
1. Open database in Notion
2. Click "⋯" (top right)
3. "Add connections" → Select your integration

**Verify all databases are shared**:
- Schools DB
- Teachers DB
- Narratives DB
- Subjects DB
- Staff Narratives DB

---

### 3. Audio Preprocessing Fails

**Error Log**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

**Solution**: Install ffmpeg

**macOS**:
```bash
brew install ffmpeg
```

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Windows**:
- Download from https://ffmpeg.org/download.html
- Add to PATH

**Verify**:
```bash
ffmpeg -version
# Should output version info
```

---

### 4. ChromaDB "Collection Not Found"

**Error Log**:
```
KeyError: 'categories'
```

**Cause**: ChromaDB not initialized or corrupted

**Solution**: Delete and reinitialize

```bash
# Stop server
# Delete ChromaDB directory
rm -rf project/.chroma_categories

# Restart server (will auto-initialize from seed_categories.json)
uvicorn project.main:app --host 0.0.0.0 --port 8000
```

**Verify seed file exists**:
```bash
ls project/seed_categories.json
# Should exist
```

---

### 5. OpenAI API Rate Limit

**Error Log**:
```
openai.error.RateLimitError: Rate limit exceeded
```

**Solutions**:

#### A. Tier Limits
Check your OpenAI tier: https://platform.openai.com/account/limits

| Tier | RPM (Requests/min) | TPM (Tokens/min) |
|------|-------------------|------------------|
| Free | 3 | 40,000 |
| Tier 1 | 500 | 200,000 |
| Tier 2 | 5,000 | 2,000,000 |

#### B. Implement Exponential Backoff
Already implemented in code:
```python
# openai library auto-retries with backoff
```

#### C. Use Alternative STT Engine
Switch from `oai` to `gemini` (free):
```python
# impact_app/service.py:60
stt_text_km, translated_en_text = decide_transcribe_model(src, "gemini")
```

---

### 6. Narrative Not Closing

**Symptoms**:
- Multiple messages sent, but still in same Narrative
- Expected time window passed

**Debug**:

#### A. Check Time Window Setting
```bash
# .env
NARRATIVE_WINDOW_MINUTES=1080  # 18 hours

# For testing, use shorter window:
NARRATIVE_WINDOW_MINUTES=1  # 1 minute
```

#### B. Check Timestamps
Add logging to see timestamp comparison:
```python
# narrative_app/service.py
logger.info(f"First timestamp: {first_ts}")
logger.info(f"New timestamp: {message_dt}")
logger.info(f"Within window: {is_within_window(first_ts, message_dt)}")
```

#### C. Timezone Mismatch
Ensure all timestamps are UTC:
```python
# Should always see "Z" suffix in logs
logger.info(f"Timestamp: {to_iso(message_dt)}")
# Correct: "2026-01-03T10:30:00Z"
# Wrong: "2026-01-03T10:30:00+07:00"
```

---

### 7. LLM Classification Always Returns "None"

**Symptoms**:
- Subject Tag or Category always "None" or empty

**Debug**:

#### A. Check LLM Response
Add logging:
```python
# narrative_app/classification.py:64
logger.info(f"LLM response: {response.choices[0].message.content}")
```

Expected:
```json
{"subject_tags": "Math"}
```

#### B. Check Prompt
Verify raw text is not empty:
```python
logger.info(f"Raw text length: {len(raw_text)}")
logger.info(f"Raw text preview: {raw_text[:100]}")
```

#### C. Model Availability
Check if model exists:
```bash
# gpt-4.1-mini may not be available in all regions
# Try alternative:
OPENAI_LLM_MODEL=gpt-4o-mini
```

---

## Debugging Techniques

### Enable Debug Logging

**Temporary** (in code):
```python
# project/main.py:14
logging.basicConfig(level=logging.DEBUG)
```

**Environment variable**:
```bash
export LOG_LEVEL=DEBUG
uvicorn project.main:app --log-level debug
```

**View specific module**:
```python
logging.getLogger('narrative_app.service').setLevel(logging.DEBUG)
```

---

### Test Webhook Locally

Use `curl` to simulate Telegram update:

**Narrative Bot**:
```bash
curl -X POST http://localhost:8000/telegram/narrative/webhook \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${NARRATIVE_TELEGRAM_SECRET_TOKEN}" \
  -d '{
    "update_id": 123456789,
    "message": {
      "message_id": 1,
      "from": {"id": 123, "first_name": "Test"},
      "chat": {"id": -456, "title": "Test School"},
      "date": 1735902600,
      "text": "Test message"
    }
  }'
```

**Impact Bot**:
```bash
curl -X POST http://localhost:8000/telegram/impact/webhook \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${IMPACT_TELEGRAM_SECRET_TOKEN}" \
  -d '{
    "update_id": 987654321,
    "message": {
      "message_id": 2,
      "from": {"id": 789, "first_name": "Trainer"},
      "chat": {"id": -111, "title": "Test Training"},
      "date": 1735902700,
      "voice": {
        "file_id": "DUMMY_FILE_ID",
        "duration": 10
      }
    }
  }'
```

---

### Python Interactive Debugging

Use `ipdb` or `pdb`:

```python
# Install
pip install ipdb

# Add breakpoint in code
import ipdb; ipdb.set_trace()

# Run server
uvicorn project.main:app --reload
```

**ipdb Commands**:
- `n`: Next line
- `s`: Step into function
- `c`: Continue
- `p variable`: Print variable
- `l`: List source code
- `q`: Quit

---

### Test Individual Functions

**Test STT**:
```python
from core.audio.stt_translate import oai_transcribe

text, conf = oai_transcribe("path/to/audio.wav")
print(f"Text: {text}")
print(f"Confidence: {conf}")
```

**Test Categorization**:
```python
from impact_app.categorization.categorizer import categorize

result = categorize("The teacher used group discussion")
print(result)
```

**Test Notion Query**:
```python
from core.notion_client import get_notion_client
from core.config import NOTION_SCHOOLS_DB_ID

notion = get_notion_client()
results = notion.databases.query(
    database_id=NOTION_SCHOOLS_DB_ID,
    filter={"property": "Telegram Chat ID", "number": {"equals": -123456}}
)
print(results)
```

---

## Log Analysis

### Log Levels

```python
logger.debug("Detailed diagnostic info")
logger.info("Normal operation")
logger.warning("Something unexpected but handled")
logger.exception("Error with full stack trace")
```

### Key Log Messages

#### Narrative DB

**Successful Processing**:
```
INFO: Saved narrative: page_id=abc123 is_new=True started_at=2026-01-03T10:30:00Z
INFO: Appended media to narrative=abc123 kind=photo url=https://...
```

**Time Window Closed**:
```
INFO: Closing narrative=abc123
INFO: Generated summary: The teacher introduced...
INFO: Synced staff narrative from narrative=abc123
```

**Errors**:
```
ERROR: Exception while handling Telegram update: <error details>
WARNING: Failed to append media(kind=photo, file_id=...) to narrative abc123: <error>
WARNING: Unknown subject tag from LLM: Physics
```

#### Impact DB

**Successful Processing**:
```
INFO: Received voice message, file_id=AwACAgQAAxkBAAIBB2...
INFO: Training space ensured: page_id=xyz789, db_id=def456
INFO: STT complete: 45 seconds of audio transcribed
INFO: Categorization: category=2a:Individual Character, confidence=0.95
INFO: Saved to Notion: page_id=ghi789
```

**Errors**:
```
ERROR: ensure_training_space failed: <error>
ERROR: Audio preprocessing failed: <error>
WARNING: ChromaDB query returned no results
```

---

## Notion API Issues

### Rate Limits

**Limit**: 3 requests per second

**Symptoms**:
- `notion_client.errors.APIResponseError: rate_limited`

**Solutions**:

#### A. Add Delay Between Requests
```python
import time

for item in items:
    process_item(item)
    time.sleep(0.35)  # ~3 requests/second
```

#### B. Batch Operations
Use `databases.query` with pagination instead of multiple `pages.retrieve` calls

---

### Page Not Found

**Error**:
```
notion_client.errors.APIResponseError: Could not find page with ID: abc123
```

**Causes**:

1. **Page was deleted**: Check in Notion
2. **Integration not shared**: Share page with integration
3. **Wrong workspace**: Verify `NOTION_ROOT_PAGE_ID` is in correct workspace

---

### Property Type Mismatch

**Error**:
```
notion_client.errors.APIResponseError: body failed validation: body.properties.Category.select.name should be a string
```

**Cause**: Wrong property type or format

**Solution**: Check property type in Notion:
```python
# Get database schema
db = notion.databases.retrieve(database_id=db_id)
print(db["properties"]["Category"])
# Output: {"select": {"options": [...]}}
```

Ensure correct format:
```python
# Select property
{"select": {"name": "Math"}}

# Rich Text property
{"rich_text": [{"text": {"content": "Text here"}}]}
```

---

## Telegram Bot Issues

### Webhook SSL Certificate Error

**Error in Telegram**:
```
SSL certificate problem: unable to get local issuer certificate
```

**Cause**: Invalid SSL certificate on server

**Solutions**:

1. **Use Cloudflare Tunnel** (for development):
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

2. **Use valid SSL certificate** (production):
   - Let's Encrypt (free)
   - Cloudflare proxy
   - AWS Certificate Manager

---

### File Download Fails

**Error**:
```
requests.exceptions.HTTPError: 404 Client Error: Not Found
```

**Cause**: File URL expired (Telegram file links are temporary)

**Solution**: Download immediately after receiving update

```python
# Correct: Download in same request
file_url = tg_get_file_url(file_id, token)
with requests.get(file_url, stream=True, timeout=180) as r:
    # Process immediately
```

**Avoid**: Storing file_id for later download (will expire)

---

### Bot Spam Protection

**Symptoms**:
- Bot stops responding
- `429 Too Many Requests` error

**Cause**: Too many messages sent too quickly

**Solution**: Implement rate limiting

```python
import time
from collections import defaultdict

last_message_time = defaultdict(float)

def rate_limited_send_message(chat_id, token, text):
    now = time.time()
    if now - last_message_time[chat_id] < 1.0:  # 1 message/second per chat
        time.sleep(1.0)

    tg_send_message(chat_id, token, text)
    last_message_time[chat_id] = time.time()
```

---

## Audio Processing Issues

### VAD Removes All Audio

**Symptoms**:
- Preprocessed audio is very short or empty
- STT returns empty string

**Cause**: VAD aggressiveness too high

**Solution**: Lower VAD aggressiveness

```python
# core/audio/audio_preprocess.py
preprocessed = preprocess_for_stt(src_path, vad_aggr=1)  # Default is 2
```

**Aggressiveness guide**:
- `0`: Keep almost everything (lots of noise)
- `1`: Moderate (good for noisy environments)
- `2`: **Default** (balanced)
- `3`: Aggressive (may cut speech in very noisy audio)

---

### "Underwater" Sound After Preprocessing

**Cause**: Noise reduction too aggressive

**Solution**: Reduce `prop_decrease`

```python
# core/audio/audio_preprocess.py:129
y = nr.reduce_noise(y=y, sr=sr, prop_decrease=0.4)  # Default is 0.6
```

---

### STT Returns Wrong Language

**Symptoms**:
- Khmer audio transcribed as Thai, Lao, or Burmese

**Solution**: Ensure language code is correct

**OpenAI**:
```python
resp = client.audio.transcriptions.create(
    model="gpt-4o-transcribe",
    file=f,
    language="km",  # ISO 639-1 code for Khmer
    prompt="The audio is in Khmer(km). Write Khmer scripts accurately."
)
```

**ElevenLabs**:
```python
transcript = client.audio.transcribe(
    audio=f,
    model="scribe_v1",
    language_code="khm"  # ISO 639-3 code for Khmer
)
```

---

## Performance Optimization

### Slow Audio Processing

**Symptoms**:
- Audio processing takes >60 seconds
- Telegram webhook timeout

**Solutions**:

#### A. Skip Preprocessing for Short Audio
```python
if duration < 10:  # seconds
    # Skip preprocessing for very short clips
    stt_text, _ = oai_transcribe(src_path)
else:
    preprocessed = preprocess_for_stt(src_path)
    stt_text, _ = oai_transcribe(preprocessed)
```

#### B. Use Faster STT Engine
```python
# Gemini is faster than OpenAI Whisper
stt_km, en = decide_transcribe_model(src, "gemini")
```

#### C. Reduce Chunk Overlap
```python
# core/audio/stt_chunking.py
chunks = split_wav_to_chunks(wav_path, chunk_sec=30, overlap_sec=0.5)  # Default is 1.5
```

---

### High Memory Usage

**Symptoms**:
- Server runs out of memory
- `MemoryError` in logs

**Solutions**:

#### A. Clean Up Temp Files
```python
import tempfile

with tempfile.TemporaryDirectory() as td:
    # All files in td are automatically deleted when exiting block
    src = os.path.join(td, "audio.wav")
    # ... process audio ...
# Temp directory and contents are now deleted
```

#### B. Limit Concurrent Processing
Use FastAPI's `BackgroundTasks` naturally limits concurrency

#### C. Process Large Files in Streaming Mode
```python
with requests.get(file_url, stream=True, timeout=180) as r:
    r.raise_for_status()
    with open(dst, 'wb') as f:
        for chunk in r.iter_content(8192):  # 8KB chunks
            f.write(chunk)
```

---

### Database Query Slow

**Symptoms**:
- Notion queries take >5 seconds

**Solutions**:

#### A. Add Filters to Narrow Results
```python
# Bad: Fetch all, filter in Python
results = notion.databases.query(database_id=db_id)
matching = [r for r in results["results"] if r["properties"]["School"]["relation"]]

# Good: Filter in query
results = notion.databases.query(
    database_id=db_id,
    filter={"property": "School", "relation": {"is_not_empty": True}}
)
```

#### B. Use Page Size
```python
results = notion.databases.query(
    database_id=db_id,
    page_size=10  # Default is 100
)
```

#### C. Cache Frequently Accessed Data
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_subject_by_name(name: str) -> str:
    # Cached for repeated queries
    results = notion.databases.query(
        database_id=NOTION_SUBJECTS_DB_ID,
        filter={"property": "Name", "title": {"equals": name}}
    )
    return results["results"][0]["id"] if results["results"] else None
```

---

## Emergency Procedures

### Reset Everything

If system is completely broken:

```bash
# 1. Stop server
# Ctrl+C or kill process

# 2. Clear ChromaDB
rm -rf project/.chroma_categories

# 3. Clear chat registry
rm -rf project/.runtime/chat_registry.json

# 4. Restart server
uvicorn project.main:app --host 0.0.0.0 --port 8000

# 5. Reset Telegram webhooks
curl -X POST "https://api.telegram.org/bot<NARRATIVE_TOKEN>/deleteWebhook"
curl -X POST "https://api.telegram.org/bot<IMPACT_TOKEN>/deleteWebhook"

# 6. Set webhooks again
curl -X POST "https://api.telegram.org/bot<NARRATIVE_TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/telegram/narrative/webhook&secret_token=<SECRET>"

curl -X POST "https://api.telegram.org/bot<IMPACT_TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/telegram/impact/webhook&secret_token=<SECRET>"
```

---

### Contact Support

If issues persist:

1. **Check logs**: Collect last 100 lines
   ```bash
   # If using systemd
   journalctl -u impact_db -n 100

   # If using Docker
   docker logs impact_db --tail 100
   ```

2. **Gather system info**:
   ```bash
   python --version
   pip list | grep -E "(fastapi|notion|openai|langchain)"
   ffmpeg -version
   ```

3. **Create issue**: https://github.com/your-repo/issues
   - Include logs, system info, and steps to reproduce

---

## Next Steps

- Back to setup: [02_setup.md](02_setup.md)
- Back to overview: [01_overview.md](01_overview.md)
