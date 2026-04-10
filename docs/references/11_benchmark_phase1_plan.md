# Benchmark Phase 1 — Console Output

## Goal

Run each STT / translation API model against the same audio and display results side-by-side in the console.
No production code changes. No Notion integration yet.

## Directory Structure

```
tests/
├── conftest.py              # Shared setup
├── audio_samples/           # Test audio files
│   └── sample_km_01.wav
└──  benchmark_stt.py         # STT benchmark → console
```

## File Responsibilities

### conftest.py — Shared Setup

**Role:** Prepare the Python environment so that benchmark scripts can import production code.

**Why it's needed:** When running `python tests/benchmark_stt.py`, Python only knows about the `tests/` directory. Production code lives in `project/core/`, which Python cannot find by default. `conftest.py` bridges this gap.

**What it does:**

1. Load `.env` from project root (makes API keys available via `os.getenv()`)
2. Add `project/` to `sys.path` (allows `from core.audio.stt_translate import ...`)

**Contents:**

```python
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent        # impact_db/
PROJECT_DIR = ROOT_DIR / "project"                       # impact_db/project/

load_dotenv(ROOT_DIR / ".env")

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
```

**How benchmark scripts use it:**

```python
# benchmark_stt.py — must be the first import
import conftest

from core.audio.stt_translate import oai_transcribe, transcribe_gemini_km
```

### audio_samples/ — Test Audio

- Place Khmer `.ogg` or `.wav` files here manually
- Add to `.gitignore` (large files should not be committed)

### benchmark_stt.py — STT Quality Comparison

**Input:** Audio files from `audio_samples/`

**What it does:** Call each STT model and print Khmer transcription results with latency.

**Functions called** (from `project/core/audio/stt_translate.py`):

| Model | Function | Returns |
|-------|----------|---------|
| OpenAI | `oai_transcribe()` | Khmer text |
| Gemini | `transcribe_gemini_km()` | Khmer text |

**Output example:**

```
=== sample_km_01.wav ===
[Gemini]      ខ្មែរ ...       (3.2s)
[OAI]         ខ្មែរ ...       (4.1s)
[AssemblyAI]  ខ្មែរ ...       (5.0s)
[Gladia]      ខ្មែរ ...       (4.8s)
[ElevenLabs]  ខ្មែរ ...       (2.8s)
```

### benchmark_translate.py — Translation Quality Comparison

**Input:** Khmer text (copy from `benchmark_stt.py` output or type manually)

**What it does:** Call each translation model and print English results with latency.

**Functions called** (from `project/core/audio/stt_translate.py`):

| Model | Function |
|-------|----------|
| OpenAI | `oai_translate_km_to_en()` |
| Gemini | `translate_gemini_km_to_en()` |

**Output example:**

```
=== Input Khmer text ===
[OAI]     English translation ...    (1.2s)
[Gemini]  English translation ...    (0.9s)
```

## Flow

```
audio_samples/sample.wav
        │
        ▼
  benchmark_stt.py        → Console: Khmer text per model + latency
```

## How to Run

```bash
# STT benchmark
python tests/benchmark_stt.py
```
