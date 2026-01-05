# Docker デプロイガイド

**日付**: 2026-01-05
**対象**: AWS Lightsail (Singapore) - impact-narrative-db-test
**デプロイ方法**: Docker + Docker Compose

---

## 📋 前提条件

以下が完了していることを確認してください:

- ✅ AWS Lightsailインスタンスが作成済み
- ✅ 静的IPアドレスが割り当て済み
- ✅ ファイアウォール設定完了 (SSH, TCP 8000, HTTP, HTTPS)
- ✅ SSH接続確認済み
- ✅ Docker & Docker Compose インストール済み

---

## 🚀 デプロイ手順

### ステップ1: Gitリポジトリのクローン

```bash
# SSH接続してサーバーにログイン
ssh -i ~/Downloads/LightsailDefaultKey-ap-southeast-1.pem ubuntu@<静的IPアドレス>

# ホームディレクトリに移動
cd ~

# Gitリポジトリをクローン
# まず、SSH鍵をGitHubに登録（未登録の場合）
ssh-keygen -t ed25519 -C "ubuntu@impact-narrative-db-test"
cat ~/.ssh/id_ed25519.pub
# → この公開鍵をGitHub Settings → SSH keys に追加

# リポジトリをクローン
git clone git@github.com:<your-org>/impact_db.git
cd impact_db
```

---

### ステップ2: .env.testファイルの作成

```bash
# テンプレートをコピー
cp .env.test.template .env.test

# .env.testを編集
nano .env.test
```

**設定内容** (実際の値に置き換えてください):

```bash
ENVIRONMENT=test
PUBLIC_BASE_URL=http://<静的IPアドレス>:8000

GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json

OPENAI_API_KEY=sk-proj-XXXXXX
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini

NARRATIVE_TELEGRAM_BOT_TOKEN=XXXXXX:XXXXXX
NARRATIVE_TELEGRAM_SECRET_TOKEN=XXXXXX

IMPACT_TELEGRAM_BOT_TOKEN=XXXXXX:XXXXXX
IMPACT_TELEGRAM_SECRET_TOKEN=XXXXXX

NOTION_API_KEY=ntn_XXXXXX
NOTION_ROOT_PAGE_ID=XXXXXX
NOTION_DATABASE_ID=XXXXXX
NOTION_SCHOOLS_DB_ID=XXXXXX
NOTION_TEACHERS_DB_ID=XXXXXX
NOTION_NARRATIVES_DB_ID=XXXXXX
NOTION_SUBJECTS_DB_ID=XXXXXX
NOTION_STAFF_NARRATIVES_DB_ID=XXXXXX

CATEGORY_MODE=hybrid
CHROMA_DIR=.chroma_categories
CATEGORY_SEED_PATH=seed_categories.json

NARRATIVE_WINDOW_MINUTES=1
```

保存して終了: `Ctrl + X` → `Y` → `Enter`

---

### ステップ3: Google Cloud認証情報のアップロード

#### オプション1: ローカルからSCP

```bash
# ローカルマシンから実行
scp -i ~/Downloads/LightsailDefaultKey-ap-southeast-1.pem \
  /path/to/service-account.json \
  ubuntu@<静的IPアドレス>:~/impact_db/credentials/
```

#### オプション2: サーバー上で直接作成

```bash
# サーバー上で実行
mkdir -p ~/impact_db/credentials
nano ~/impact_db/credentials/service-account.json
# JSONの内容を貼り付け
# Ctrl + X → Y → Enter で保存
```

---

### ステップ4: 必要なディレクトリの作成

```bash
cd ~/impact_db

# ChromaDBとランタイムデータ用ディレクトリ
mkdir -p .chroma_categories .runtime

# パーミッション確認
ls -la
```

---

### ステップ5: Dockerイメージのビルド

```bash
# Dockerイメージをビルド
docker compose build

# ビルド完了を確認
docker images | grep impact
```

---

### ステップ6: Dockerコンテナの起動

```bash
# バックグラウンドで起動
docker compose up -d

# ログを確認
docker compose logs -f
```

**正常起動の確認**:
```
impact-narrative-db | INFO:     Started server process [1]
impact-narrative-db | INFO:     Waiting for application startup.
impact-narrative-db | INFO:     Application startup complete.
impact-narrative-db | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

`Ctrl + C` でログ表示を終了（コンテナは継続実行）

---

### ステップ7: ヘルスチェック

```bash
# コンテナの状態確認
docker compose ps

# ヘルスチェックエンドポイントを確認
curl http://localhost:8000/healthz
# → 期待される応答: {"status": "healthy"} または類似のレスポンス

# ローカルマシンから確認
curl http://<静的IPアドレス>:8000/healthz
```

---

## 🔧 管理コマンド

### コンテナの管理

```bash
# コンテナの状態確認
docker compose ps

# ログの確認
docker compose logs -f

# コンテナの停止
docker compose stop

# コンテナの起動
docker compose start

# コンテナの再起動
docker compose restart

# コンテナの停止と削除
docker compose down

# コンテナ、イメージ、ボリュームをすべて削除
docker compose down -v --rmi all
```

### コードの更新

```bash
cd ~/impact_db

# 最新コードをプル
git pull origin main

# イメージを再ビルド
docker compose build

# コンテナを再起動
docker compose up -d

# ログ確認
docker compose logs -f
```

---

## 🔍 トラブルシューティング

### 問題1: コンテナが起動しない

```bash
# ログを確認
docker compose logs

# 考えられる原因:
# - .env.testファイルが存在しない → 作成する
# - credentials/service-account.json がない → アップロードする
# - ポート8000が既に使用されている → sudo lsof -i :8000 で確認
```

### 問題2: ヘルスチェックが失敗する

```bash
# コンテナ内でcurlを実行
docker compose exec app curl -f http://localhost:8000/healthz

# アプリケーションログを確認
docker compose logs app

# 考えられる原因:
# - アプリケーションが起動していない
# - /healthz エンドポイントが実装されていない
# - 環境変数が正しく設定されていない
```

### 問題3: Telegramからのリクエストが届かない

```bash
# Webhookを再設定（ローカルマシンから）
curl -X POST "https://api.telegram.org/bot<NARRATIVE_BOT_TOKEN>/setWebhook" \
  -d "url=http://<静的IPアドレス>:8000/telegram/narrative/webhook" \
  -d "secret_token=<SECRET_TOKEN>"

# Webhook情報を確認
curl "https://api.telegram.org/bot<NARRATIVE_BOT_TOKEN>/getWebhookInfo"

# 考えられる原因:
# - ファイアウォールでポート8000が開いていない
# - WebhookのURLが間違っている
# - コンテナが起動していない
```

---

## 📊 ディスク使用量の確認

```bash
# Dockerディスク使用量
docker system df

# 不要なイメージ・コンテナの削除
docker system prune -a
```

---

## 🔄 自動再起動の設定

docker-compose.ymlで `restart: unless-stopped` を設定済みのため、サーバー再起動時に自動的にコンテナが起動します。

確認:
```bash
# サーバーを再起動
sudo reboot

# 再ログイン後
docker compose ps
# → コンテナが自動的に起動していることを確認
```

---

## 📌 次のステップ

- [ ] Telegram Webhookの設定
- [ ] 実際のメッセージでテスト
- [ ] ログの監視設定
- [ ] バックアップ戦略の検討（.chroma_categories, .runtimeディレクトリ）

---

**ステータス**: デプロイ準備完了
**所要時間**: 約30-45分
