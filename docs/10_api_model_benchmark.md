# API Model Benchmark — STT & Translation

## Goal

Compare the quality and performance of STT / translation API models (Gemini, OpenAI, AssemblyAI, Gladia, ElevenLabs) **without modifying production code** in `project/`.

## Two-Phase Approach

### Phase 1: Console Output

Run each model against the same audio samples and print results side-by-side in the terminal.

### Phase 2: Notion Output

Export the benchmark results to a dedicated Notion database, reusing the production Notion client pattern.

## Directory Structure

```
tests/
├── conftest.py                # Shared setup (.env loading, sys.path for project/)
├── audio_samples/             # Test audio files
│   └── .gitkeep
│
├── benchmark_stt.py           # Phase 1 — STT quality comparison → console
├── benchmark_translate.py     # Phase 1 — Translation quality comparison → console
│
├── output/                    # Saved results (JSON) from Phase 1
│   └── .gitkeep
│
└── notion_export.py           # Phase 2 — Read output/ and push to Notion
```

## File Responsibilities

### conftest.py

- Load `.env` from project root
- Add `project/` to `sys.path` so production modules can be imported

### benchmark_stt.py (Phase 1)

- Read audio files from `audio_samples/`
- Call each STT model via functions in `project/core/audio/stt_translate.py`
- Print Khmer transcription results side-by-side with latency
- Save results as JSON to `output/`

Example console output:

```
=== sample_km_01.wav ===
[Gemini]      ខ្មែរ ...       (3.2s)
[OAI]         ខ្មែរ ...       (4.1s)
[AssemblyAI]  ខ្មែរ ...       (5.0s)
[Gladia]      ខ្មែរ ...       (4.8s)
[ElevenLabs]  ខ្មែរ ...       (2.8s)
```

### benchmark_translate.py (Phase 1)

- Take Khmer text (from STT results or manual input) and run through each translation model
- Print English translations side-by-side with latency

### notion_export.py (Phase 2)

- Reuse `project/core/notion_client.py` (`get_notion_client()`) for API access
- Write to a **test-dedicated Notion database** (separate DB ID from production)
- Read results from `output/` JSON files and create Notion pages

## Key Principles

| Principle | Detail |
|-----------|--------|
| **No production code changes** | Import functions from `project/` directly; never modify them |
| **Isolated Notion DB** | Use a separate Notion database ID for test results, not the production DB |
| **Phase separation** | Phase 1 saves to `output/` → Phase 2 reads from `output/`. Each phase can run independently |
| **Incremental rollout** | Start with Phase 1 (console only). Add Phase 2 (Notion) after reviewing initial results |

## How to Run

```bash
# Phase 1: STT benchmark
python tests/benchmark_stt.py

# Phase 1: Translation benchmark
python tests/benchmark_translate.py

# Phase 2: Export results to Notion
python tests/notion_export.py
```
