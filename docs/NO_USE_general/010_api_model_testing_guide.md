# APIモデル検証の一般的な方法

## 概要

本番コード（`project/`）を変更せずに、STT・翻訳APIモデル（Gemini, OpenAI, AssemblyAI, Gladia, ElevenLabsなど）の品質・性能を比較検証するための方法論をまとめる。

## 1. テストの種類

### A. 接続・動作確認テスト（Smoke Test）

- APIキーが有効か
- リクエストが正常に通るか（短い音声1つで確認）
- レスポンスの形式が期待通りか

### B. 品質比較テスト（Quality Benchmark）

- 同じ音声ファイルを全モデルに投げる
- 結果を横並びで出力して人間が評価する
- 可能なら「正解テキスト」を用意してWER（Word Error Rate）等で定量比較

### C. 非機能テスト（Performance）

- レイテンシ（応答速度）
- チャンク数が増えた時の挙動
- エラー時のハンドリング（タイムアウト、レート制限）

## 2. 実行方法の使い分け

| 方法 | 向いてるケース |
|------|--------------|
| **pytest** | 接続確認・回帰テスト。pass/failで自動判定できるもの |
| **スクリプト直接実行** | 品質比較。結果を表示して人間が目で見て判断するもの |

STT・翻訳は「正解が一意に決まらない」ため、品質比較はスクリプト実行→結果を表示の方が現実的。

## 3. 典型的な進め方

```
Step 1: テスト用音声を用意（短い5-10秒 + 実際の長さのもの）
Step 2: Smoke Test — 各APIが動くことを確認
Step 3: 同一音声で全モデルを実行 → 結果を並べて出力
Step 4: 結果を見て、精度・速度・コストで判断
```

## 4. 結果の出力形式

標準的にはコンソールに比較表を出す形式。

```
=== test_audio_01.wav ===
[Gemini STT]   ខ្មែរ ...
[OAI STT]      ខ្មែរ ...
[ElevenLabs]   ខ្មែរ ...

[Gemini EN]    English ...
[OAI EN]       English ...

Latency: Gemini=3.2s | OAI=4.1s | ElevenLabs=2.8s
```

## 5. ディレクトリ構成

```
impact_db/
├── project/                 # 本番コード（触らない）
├── tests/                   # APIテスト用
│   ├── conftest.py          # 共通設定（env読み込み、パス）
│   ├── audio_samples/       # テスト音声ファイル
│   │   └── sample_km_01.wav
│   ├── test_smoke.py        # 各APIの接続確認（pytest）
│   ├── benchmark_stt.py     # STT品質比較（スクリプト実行）
│   └── benchmark_translate.py  # 翻訳品質比較（スクリプト実行）
```

- `test_*.py` → `pytest tests/` で自動テスト
- `benchmark_*.py` → `python tests/benchmark_stt.py` で手動実行・目視確認

## 6. 本番コードとの分離

- `tests/` から `project/` の関数をimportして使う（`sys.path`追加）
- `.dockerignore` に `tests/` を追加し、本番イメージに含めない
- テスト用の設定は `conftest.py` に集約する
