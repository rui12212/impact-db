# v1_portfolio Architecture

## Overview

Telegram Bot Webhook → `service.py` (routing & business logic) → `notion_repos.py` (Notion DB CRUD) → Notion Database

The system receives messages from a Telegram Bot and persists them as "Portfolio" records in Notion.

---

## Recording Lifecycle

```
[Open] ──(time elapsed or /new)──→ [Closed] ──(auto)──→ [Translated]
```

| Transition | Condition | service.py | notion_repos.py |
|-----------|-----------|------------|-----------------|
| **Create (Open)** | No open record exists for the user | `handle_telegram_data` | `decide_and_get_or_create_portfolio` → `create_portfolio` |
| **Append (stay Open)** | Open record exists AND `last_edited_time` within `WINDOW_MINUTES` | `handle_telegram_data` | `decide_and_get_or_create_portfolio` → `append_and_update_portfolio_children` |
| **Confirmation dialog** | Open record exists AND `last_edited_time` exceeds `WINDOW_MINUTES` | `handle_telegram_data` → `pending_store` に保存 → InlineKeyboard送信 | `decide_and_get_or_create_portfolio` returns `needs_confirmation=True` |
| **CONTINUE (after dialog)** | User presses "CONTINUE" button | `handle_callback_query` (callback_data=`"continue"`) | `append_and_update_portfolio_children` |
| **START NEW (after dialog)** | User presses "START NEW" button | `handle_callback_query` (callback_data=`"finish"`) | `check_and_close_portfolio` → `translate_note_and_update_translated_note` → `create_portfolio` |
| **Close via /new** | User sends `/new` command | `new_command` | `check_and_close_portfolio` |
| **Translate** | Triggered immediately after Close | `new_command` / `handle_callback_query` | `translate_note_and_update_translated_note` |

---

## Confirmation Dialog Flow (when WINDOW_MINUTES exceeded)

```
User sends message
  ↓ (last_edited_time > WINDOW_MINUTES)
Bot: "CONTINUE previous session? or START NEW?"
  ├─ CONTINUE → append to existing open record
  └─ START NEW → close all open records + translate → create new record
```

---

## Layer Responsibilities

| Layer | File | Role |
|-------|------|------|
| Routing & Logic | `service.py` | Telegram event dispatch, confirmation flow, media group buffering |
| Repository | `notion_repos.py` | Notion API operations (CRUD, time-window check, translation trigger) |
| Models | `models.py` | Data classes (`TelegramUserInfo`, `PortfolioDecisionResult`) |
| External | R2, OpenAI, Notion | Media storage, STT, database |

---

## Transcribe & Translate — Detailed Guide

This section explains where and how transcription (STT) and translation happen, so you know exactly which files to modify.

---

### File Map (which file does what)

```
project/
├── v1_portfolio/
│   ├── service.py                    ← Entry point: receives audio, calls STT
│   └── notion/
│       └── notion_repos.py           ← Calls translation after Close
│
├── core/audio/
│   ├── helpers_audio.py              ← pick_audio_from_message(): detects audio type from Telegram message
│   ├── audio_preprocess.py           ← preprocess_for_stt(): noise reduction, EQ, VAD trim
│   ├── stt_chunking.py              ← split_wav_to_chunks(): splits WAV into 30s chunks
│   └── stt_translate.py             ← All STT & translation functions live here
```

---

### Transcribe (STT) — Full Flow

```
[Telegram audio message arrives]
        │
        ▼
service.py: handle_telegram_data()
        │
        ├─ pick_audio_from_message()          ← helpers_audio.py
        │   (detects voice/audio/document from Telegram message fields)
        │
        ├─ Download file from Telegram API    ← tg_get_file_url()
        │
        ▼
service.py: calls oai_transcribe(file_path)   ← stt_translate.py
        │
        ▼
┌─────────────────────────────────────────────┐
│  oai_transcribe() internal steps:           │
│                                             │
│  1. preprocess_for_stt(file_path)           │  ← audio_preprocess.py
│     ├─ Convert to 16kHz mono WAV            │
│     ├─ Noise reduction (noisereduce lib)    │
│     ├─ Band-pass filter (70Hz–7kHz)         │
│     ├─ Vowel EQ boost (700Hz, 1500Hz)       │
│     ├─ Peak normalize (-1dBFS)              │
│     ├─ AGC + compression                    │
│     └─ VAD trim (remove silence)            │
│                                             │
│  2. split_wav_to_chunks(wav, 30000ms, 0ms)  │  ← stt_chunking.py
│     └─ Returns [(chunk_path, start, end)]   │
│                                             │
│  3. For each chunk:                         │
│     └─ OpenAI gpt-4o-transcribe API call    │
│                                             │
│  4. Join all chunk texts with "\n"          │
│     └─ Return full transcript string        │
└─────────────────────────────────────────────┘
        │
        ▼
service.py: note_text = transcript
        │
        ▼
notion_repos.py: save to Notion "note" property
```

**Key point**: To change the STT model, edit `oai_transcribe()` in `stt_translate.py`, or use `decide_transcribe_model()` to route by model name.

---

### Translate — Full Flow

Translation happens at a **different timing** than transcription.

```
[Portfolio record gets Closed]
        │  (triggered by /new command or "START NEW" button)
        │
        ▼
service.py: new_command() or handle_callback_query()
        │
        ├─ check_and_close_portfolio(user_id)   ← notion_repos.py
        │   └─ Returns list of closed page IDs
        │
        ▼
For each closed page:
        │
        ▼
notion_repos.py: translate_note_and_update_translated_note(page_id)
        │
        ├─ 1. Retrieve "note" property from Notion page
        │
        ├─ 2. Call portfolio_translate_note_km_to_en(note, "gpt-4.1-mini")
        │      └─ stt_translate.py
        │      └─ System prompt: "Translate Khmer→English, keep English as-is,
        │         preserve original order, do not summarize"
        │
        └─ 3. Save result to "translated_note" property in Notion
```

**Key point**: To change the translation model or prompt, edit `portfolio_translate_note_km_to_en()` in `stt_translate.py`.

---

### How to Modify: Quick Reference

| What you want to change | File to edit | Function |
|------------------------|-------------|----------|
| STT model (e.g. switch from OpenAI to Gemini) | `core/audio/stt_translate.py` | `oai_transcribe()` or add routing in `decide_transcribe_model()` |
| Audio preprocessing (noise, EQ, VAD) | `core/audio/audio_preprocess.py` | `preprocess_for_stt()` |
| Chunk size or overlap | `core/audio/stt_chunking.py` | `split_wav_to_chunks()` params |
| Translation model or prompt | `core/audio/stt_translate.py` | `portfolio_translate_note_km_to_en()` |
| When translation is triggered | `v1_portfolio/notion/notion_repos.py` | `translate_note_and_update_translated_note()` |
| Which audio types are recognized | `core/audio/helpers_audio.py` | `pick_audio_from_message()` |

---

### Available STT Models in `stt_translate.py`

| Function | Provider | Input | Output |
|----------|----------|-------|--------|
| `oai_transcribe` | OpenAI (`gpt-4o-transcribe`) | audio file | transcribed text (any language) |
| `transcribe_assemblyai_km_to_en` | AssemblyAI | audio file | (Khmer text, English translation) |
| `transcribe_gladia_km_to_en` | Gladia | audio file | (Khmer text, English translation) |
| `transcribe_elevenlabs_km` | ElevenLabs Scribe | audio file | Khmer text only |
| `transcribe_gemini_km` | Google Gemini 2.5 Flash | audio file | Khmer text only |
| `transcribe_gemini_en` | Google Gemini 2.5 Flash | audio file | English text only |

`decide_transcribe_model(file_path, model_name)` routes to the appropriate function based on `model_name` string.

---

### Important Notes

- **Transcribe timing**: happens immediately when audio is received (real-time, inside `handle_telegram_data`)
- **Translate timing**: happens only when a record is **closed** (not real-time)
- **AssemblyAI / Gladia** do STT + translation in one API call; **OpenAI / ElevenLabs / Gemini** require a separate translation step
- Preprocessing is shared across all models — always goes through `preprocess_for_stt()` first
