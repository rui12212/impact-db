# Impact DB 月間API料金見積もり

**Date**: 2026-02-13
**Target**: Impact DB - 月間運用コストの試算
**Status**: 見積もり

---

## 1. 前提条件

| 項目 | 値 |
|------|-----|
| 月間ファイル数 | 60（英語50 + クメール語10）|
| 1ファイルの長さ | 3分（180秒）|
| 音声チャンク設定 | 30秒チャンク / 1.5秒オーバーラップ → **7チャンク/ファイル** |
| 音声トークンレート | 32 tokens/秒（Gemini公式仕様） |

---

## 2. API単価一覧

| API | 入力単価 | 出力単価 |
|-----|---------|---------|
| **Gemini 2.5 Flash**（テキスト入力） | $0.30 / 1M tokens | $2.50 / 1M tokens（thinking込み） |
| **Gemini 2.5 Flash**（音声入力） | $1.00 / 1M tokens | 同上 |
| **OpenAI text-embedding-3-small** | $0.02 / 1M tokens | — |
| **OpenAI gpt-4o-mini** | $0.15 / 1M tokens | $0.60 / 1M tokens |

参照元:
- https://ai.google.dev/gemini-api/docs/pricing
- https://platform.openai.com/docs/pricing

---

## 3. 処理フロー別API呼び出し

### 3.1 英語音声ファイル（1件あたり）

```
音声ファイル (3分)
    │
    ▼
[1] detect_language()        → Gemini (audio 30s = 960 tokens)
    │
    ▼
[2] transcribe_gemini_en()   → Gemini (audio 7chunks = 6,048 tokens)
    │
    ▼
[3] remove_fillers()         → Gemini (text ~750 tokens)
    │
    ▼
[4] categorize()             → OpenAI Embedding + gpt-4o-mini
```

### 3.2 クメール語音声ファイル（1件あたり）

```
音声ファイル (3分)
    │
    ▼
[1] detect_language()        → Gemini (audio 30s = 960 tokens)
    │
    ▼
[2] transcribe_gemini_km()   → Gemini (audio 7chunks = 6,048 tokens)
    │
    ▼
[3] translate_gemini_km_to_en() → Gemini (text ~630 tokens)
    │
    ▼
[4] categorize()             → OpenAI Embedding + gpt-4o-mini
```

---

## 4. 料金計算の詳細

### 4.1 英語ファイル 1件あたり

| ステップ | 関数 | 入力コスト | 出力コスト | 小計 |
|---------|------|-----------|-----------|------|
| 言語検出 | `detect_language()` | 960×$1.00/1M + 30×$0.30/1M = $0.00097 | 100×$2.50/1M = $0.00025 | **$0.00122** |
| 文字起こし（7chunks） | `transcribe_gemini_en()` | 6,048×$1.00/1M + 105×$0.30/1M = $0.00608 | 2,100×$2.50/1M = $0.00525 | **$0.01133** |
| フィラー除去 | `remove_fillers()` | 750×$0.30/1M = $0.00023 | 1,050×$2.50/1M = $0.00263 | **$0.00285** |
| 分類（Embedding） | `categorize()` | 600×$0.02/1M = $0.00001 | — | **$0.00001** |
| 分類（LLM） | `categorize()` | 800×$0.15/1M = $0.00012 | 100×$0.60/1M = $0.00006 | **$0.00018** |
| **英語1件 合計** | | | | **$0.01559** |

### 4.2 クメール語ファイル 1件あたり

| ステップ | 関数 | 入力コスト | 出力コスト | 小計 |
|---------|------|-----------|-----------|------|
| 言語検出 | `detect_language()` | $0.00097 | $0.00025 | **$0.00122** |
| 文字起こし（7chunks） | `transcribe_gemini_km()` | $0.00608 | $0.00525 | **$0.01133** |
| 翻訳 Km→En | `translate_gemini_km_to_en()` | 630×$0.30/1M = $0.00019 | 900×$2.50/1M = $0.00225 | **$0.00244** |
| 分類（Embedding） | `categorize()` | $0.00001 | — | **$0.00001** |
| 分類（LLM） | `categorize()` | $0.00012 | $0.00006 | **$0.00018** |
| **クメール語1件 合計** | | | | **$0.01518** |

---

## 5. 月間合計

| 言語 | ファイル数 | 1件あたり | 月額 |
|------|-----------|----------|------|
| 英語 | 50 | $0.01559 | **$0.780** |
| クメール語 | 10 | $0.01518 | **$0.152** |
| **月間合計** | **60** | | **≈ $0.93** |

---

## 6. Geminiクォータ制限との関係

現在の `GEMINI_MONTHLY_LIMIT=100` では60ファイルを処理しきれない。

| 言語 | ファイル数 | Geminiコール数/件 | 月間合計 |
|------|-----------|-----------------|---------|
| 英語 | 50 | 3（detect + transcribe + remove_fillers） | 150 |
| クメール語 | 10 | 3（detect + transcribe + translate） | 30 |
| **合計** | | | **180** |

100件目で `GeminiQuotaExceeded` が発生し、残り約27ファイルが処理不能になる。

**対応**: 月60ファイルを処理するには `.env.local` の `GEMINI_MONTHLY_LIMIT` を **180以上** に設定する必要がある。

---

## 7. 備考

- 出力トークンの見積もりにはGemini 2.5 Flashのthinking tokens（内部推論トークン）を含む推定値を使用
- 実際のthinking tokens消費量はタスクの複雑さにより変動するため、実際の料金は±30%程度の誤差がありうる
- OpenAI Embedding は入力トークンのみ課金（出力トークンなし）
- 音声チャンクのオーバーラップにより、実際に送信される音声量は元の3分より約5%多い（約189秒）
