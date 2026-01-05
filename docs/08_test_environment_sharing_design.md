# テスト環境共有設計書
# Third-Party Developer Access to Test Environment

**文書バージョン**: 1.0 (草案)
**作成日**: 2026-01-03
**作成者**: 開発チーム
**ステータス**: 草案 - レビュー待ち
**レビュワー**: プロジェクトオーナー

---

## 文書管理

| バージョン | 日付 | 作成者 | 変更内容 |
|---------|------|--------|---------|
| 0.1 | 2026-01-03 | 開発チーム | 初版草案 |
| 1.0 | TBD | 開発チーム | 承認版 |

---

## 1. エグゼクティブサマリー

### 1.1 目的
本文書は、**現在使用中のテスト環境を第三者開発者と安全に共有する**ための具体的な手順と設計を定義する。

### 1.2 スコープ
- テスト環境サーバーの選択と推奨
- テスト環境サーバーへのデプロイ手順
- 第三者開発者へのアクセス権付与方法
- API認証情報の安全な共有方法
- 開発ワークフローとGit運用
- セキュリティ対策

### 1.3 前提条件

✅ **確認済み**:
- 現在のNotion、Telegram Bot、APIキーをテスト環境として使用
- テスト環境用サーバーの契約が必要
- Dockerは使用しない（一部サーバーでは使用不可）

✅ **目標**:
- 第三者開発者がテスト環境にアクセス可能
- サーバー上でテスト環境が稼働
- 開発者がローカルでも開発・テスト可能

---

## 2. テスト環境サーバーの選択

### 2.1 サーバー選択基準

| 基準 | 要件 |
|-----|------|
| **SSH アクセス** | 必須（Pythonアプリのデプロイに必要） |
| **Python 3.9+** | 必須またはインストール可能 |
| **プロセス管理** | systemd, supervisor, screenなどが使用可能 |
| **ストレージ** | 最低 10GB（ChromaDB、ログ保存用） |
| **メモリ** | 最低 1GB（推奨 2GB以上） |
| **帯域幅** | 従量制でない、または十分な帯域 |
| **コスト** | 月額 $5〜$20 程度が目安 |
| **サポート** | 日本語サポートがあると望ましい |

### 2.2 推奨サーバー比較

#### Option 1: さくらのVPS（推奨 - 日本サーバー）

**特徴**:
- ✅ 日本のサービス、日本語サポート充実
- ✅ SSH標準対応
- ✅ Python 3.x インストール可能
- ✅ systemd使用可能
- ✅ 固定IPアドレス

**プラン**:
| プラン | 料金 | メモリ | ストレージ | 推奨度 |
|-------|------|--------|----------|-------|
| 512MB | ¥590/月 | 512MB | 25GB SSD | ⚠️ 最小限 |
| **1GB** | **¥880/月** | **1GB** | **50GB SSD** | **✅ 推奨** |
| 2GB | ¥1,780/月 | 2GB | 100GB SSD | ✅ 快適 |

**セットアップ難易度**: ⭐⭐☆☆☆（普通）

**公式サイト**: https://vps.sakura.ad.jp/

---

#### Option 2: Linode (現 Akamai Cloud Computing)

**特徴**:
- ✅ グローバルで人気のVPS
- ✅ 日本（東京）データセンター利用可能
- ✐ 管理画面は英語（日本語サポートなし）
- ✅ SSH標準対応
- ✅ Python 3.x プリインストール
- ✅ systemd使用可能

**プラン**:
| プラン | 料金 | メモリ | ストレージ | 推奨度 |
|-------|------|--------|----------|-------|
| **Nanode 1GB** | **$5/月** | **1GB** | **25GB SSD** | **✅ 推奨** |
| Linode 2GB | $10/月 | 2GB | 50GB SSD | ✅ 快適 |

**セットアップ難易度**: ⭐⭐☆☆☆（普通）

**公式サイト**: https://www.linode.com/

---

#### Option 3: DigitalOcean

**特徴**:
- ✅ シンプルで使いやすい管理画面
- ✅ 豊富なチュートリアル・ドキュメント
- ✅ 日本（シンガポール）データセンター
- ⚠️ 日本語サポートなし
- ✅ SSH標準対応
- ✅ Python 3.x プリインストール

**プラン**:
| プラン | 料金 | メモリ | ストレージ | 推奨度 |
|-------|------|--------|----------|-------|
| **Basic Droplet** | **$6/月** | **1GB** | **25GB SSD** | **✅ 推奨** |
| Regular Droplet | $12/月 | 2GB | 50GB SSD | ✅ 快適 |

**セットアップ難易度**: ⭐☆☆☆☆（簡単）

**公式サイト**: https://www.digitalocean.com/

---

#### Option 4: ConoHa VPS

**特徴**:
- ✅ GMOが運営、日本のサービス
- ✅ 日本語サポート充実
- ✅ 時間課金対応（短期テストに便利）
- ✅ SSH標準対応
- ✅ Python 3.x インストール可能

**プラン**:
| プラン | 料金 | メモリ | ストレージ | 推奨度 |
|-------|------|--------|----------|-------|
| 512MB | ¥682/月 | 512MB | 30GB SSD | ⚠️ 最小限 |
| **1GB** | **¥941/月** | **1GB** | **100GB SSD** | **✅ 推奨** |

**セットアップ難易度**: ⭐⭐☆☆☆（普通）

**公式サイト**: https://www.conoha.jp/vps/

---

#### Option 5: AWS Lightsail

**特徴**:
- ✅ Amazon Web Servicesの簡易版
- ✅ 東京リージョン利用可能
- ⚠️ AWSアカウント必要（複雑な管理画面）
- ✅ SSH標準対応
- ✅ Python 3.x プリインストール

**プラン**:
| プラン | 料金 | メモリ | ストレージ | 推奨度 |
|-------|------|--------|----------|-------|
| **$5 プラン** | **$5/月** | **1GB** | **40GB SSD** | **✅ 推奨** |
| $10 プラン | $10/月 | 2GB | 60GB SSD | ✅ 快適 |

**セットアップ難易度**: ⭐⭐⭐☆☆（やや難）

**公式サイト**: https://aws.amazon.com/lightsail/

---

### 2.3 テスト環境の決定

**✅ テスト環境**: **AWS Lightsail ($5プラン)** を使用

**選択理由**:
- カンボジアからのアクセスが高速 (40-60ms)
- 年間¥1,800安い (月額¥7,893 vs さくら¥8,043)
- 将来的な拡張性が高い (RDS、S3、CloudFront等と連携可能)
- グローバルで実績のあるインフラ

**本番環境**: 今後検討・変更の可能性あり

---

### 2.4 参考: その他サーバー選択肢

| 優先順位 | サービス | 理由 |
|---------|---------|------|
| **🥇 採用** | **AWS Lightsail ($5プラン)** | カンボジア高速、拡張性、コスト |
| 🥈 参考 | さくらのVPS (1GBプラン) | 日本語サポート、安定性 |
| 🥉 参考 | Linode (Nanode 1GB) | グローバルスタンダード |

**初心者向け**: さくらのVPS、ConoHa VPS（日本語サポート充実）
**コスト重視**: AWS Lightsail、Linode（$5/月）
**拡張性重視**: AWS Lightsail（AWSエコシステム）

---

## 3. テスト環境の構成

### 3.1 全体像

```
┌─────────────────────────────────────────────────────────────┐
│              第三者開発者のローカル環境                        │
│                                                              │
│  ├── コード: Git clone → feature ブランチで開発             │
│  ├── Notion: 共有テスト環境への読み取り専用アクセス           │
│  ├── Telegram: テスト用Bot（共有）                          │
│  ├── Webhook: ngrok/Cloudflare Tunnel（ローカルテスト用）   │
│  └── API: 共有テスト環境のAPIキー（読み取り専用）             │
│                                                              │
│  開発フロー:                                                  │
│  1. ローカルで開発・テスト                                    │
│  2. Pull Requestを作成                                       │
│  3. レビュー承認後、テスト環境サーバーにデプロイ              │
└─────────────────────────────────────────────────────────────┘
                           ↓ Git Push
┌─────────────────────────────────────────────────────────────┐
│                Git リポジトリ（GitHub/GitLab）                │
│                                                              │
│  main ブランチ: テスト環境にデプロイされる安定版               │
│  develop ブランチ: 統合テスト用                              │
│  feature/* ブランチ: 各開発者の作業ブランチ                  │
└─────────────────────────────────────────────────────────────┘
                           ↓ Deploy
┌─────────────────────────────────────────────────────────────┐
│              テスト環境サーバー（VPS）                        │
│                                                              │
│  ├── OS: Ubuntu 22.04 LTS                                   │
│  ├── コード: main ブランチから自動 or 手動デプロイ            │
│  ├── Notion: 現在使用中のワークスペース（テストデータ）        │
│  ├── Telegram: 現在使用中のBot（テストグループ）             │
│  ├── Webhook: サーバーの公開URL                             │
│  ├── API: 現在使用中のOpenAI/Google Cloudキー               │
│  └── 実行環境: Python venv + systemd                        │
│                                                              │
│  URL例: https://test-impact-db.your-domain.com              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 テスト環境のリソース

| リソース | 現状 | 第三者への共有方法 |
|---------|------|------------------|
| **Gitリポジトリ** | プライベート | 第三者を招待（Read権限） |
| **Notion** | 現在使用中のワークスペース | 読み取り専用Integrationを共有 |
| **Telegram Bot** | 現在使用中の2つのBot | Botトークンを環境変数で共有 |
| **OpenAI API** | 現在使用中のキー | `.env.example` に記載せず、個別に共有 |
| **Google Cloud** | 現在使用中のサービスアカウント | JSON keyファイルを個別に共有 |
| **テスト環境サーバー** | VPS契約 | SSH/FTPアクセスを個別に付与 |

---

## 4. テスト環境サーバーのセットアップ (AWS Lightsail)

### 4.1 AWS Lightsail インスタンスの作成

#### ステップ1: AWSアカウント作成
1. https://aws.amazon.com/ にアクセス
2. 「アカウント作成」をクリック
3. メールアドレス、パスワード、クレジットカード情報を登録
4. 電話番号認証を完了

#### ステップ2: Lightsailインスタンスの作成
1. AWS Management Consoleにログイン
2. 検索バーで「Lightsail」を検索して選択
3. 「インスタンスの作成」をクリック

**インスタンス設定**:
- **リージョン**: Tokyo (ap-northeast-1) ← カンボジアから最も近い
- **プラットフォーム**: Linux/Unix
- **OS**: Ubuntu 22.04 LTS
- **プラン**: $5/月 (1GB RAM, 1 vCPU, 40GB SSD, 1TB転送)
- **インスタンス名**: impact-db-test

4. 「インスタンスの作成」をクリック

#### ステップ3: 静的IPアドレスの割り当て
1. Lightsailダッシュボードで「ネットワーキング」タブ
2. 「静的IPの作成」をクリック
3. 作成したインスタンス「impact-db-test」にアタッチ
4. 静的IP名: impact-db-test-ip
5. 「作成」をクリック

> **重要**: 静的IPを割り当てないと、インスタンス再起動時にIPアドレスが変わります

#### ステップ4: ファイアウォール設定
1. Lightsailダッシュボードでインスタンスを選択
2. 「ネットワーキング」タブ → 「IPv4 Firewall」
3. 以下のルールを追加:

| アプリケーション | プロトコル | ポート範囲 | 説明 |
|--------------|---------|---------|------|
| SSH | TCP | 22 | SSH接続 |
| Custom | TCP | 8000 | FastAPI アプリケーション |
| HTTP | TCP | 80 | HTTP (オプション) |
| HTTPS | TCP | 443 | HTTPS (オプション) |

#### ステップ5: SSH接続
```bash
# ローカルマシンから
# Lightsailダッシュボードから秘密鍵をダウンロード
# 「アカウント」→「SSHキー」→「デフォルトキーのダウンロード」

# キーのパーミッション設定
chmod 400 ~/Downloads/LightsailDefaultKey-ap-northeast-1.pem

# SSH接続
ssh -i ~/Downloads/LightsailDefaultKey-ap-northeast-1.pem ubuntu@<静的IPアドレス>
```

または、Lightsailコンソールから直接ブラウザSSHも可能:
1. インスタンスページ → 「接続」タブ → 「ブラウザを使用して接続」

#### ステップ6: システムアップデート
```bash
# ubuntuユーザーとして実行
sudo apt update && sudo apt upgrade -y
```

> **Note**: AWS LightsailのUbuntuでは、デフォルトで`ubuntu`ユーザーがsudo権限を持っています。
> 別途deployユーザーを作成する必要はありません。

### 4.2 必要なソフトウェアのインストール

```bash
# ubuntuユーザーとして実行

# Python 3.9+ と venv
sudo apt install python3 python3-venv python3-pip -y

# ffmpeg（音声処理用）
sudo apt install ffmpeg -y

# Git (通常プリインストール済み)
sudo apt install git -y

# その他ユーティリティ
sudo apt install curl wget vim -y

# バージョン確認
python3 --version  # Python 3.10.x など
ffmpeg -version
git --version
```

### 4.3 プロジェクトのセットアップ

#### ステップ1: プロジェクトディレクトリ作成
```bash
cd ~
mkdir impact_db
cd impact_db
```

#### ステップ2: Gitリポジトリのクローン
```bash
# SSH鍵をGitHubに登録（未登録の場合）
ssh-keygen -t ed25519 -C "deploy@server"
cat ~/.ssh/id_ed25519.pub
# GitHub Settings → SSH keys → New SSH key に貼り付け

# リポジトリをクローン
git clone git@github.com:your-org/impact_db.git .
git checkout main
```

#### ステップ3: Python仮想環境の作成
```bash
python3 -m venv impact_db_env
source impact_db_env/bin/activate

# pip更新
pip install --upgrade pip

# 依存関係インストール
pip install -r requirements.txt
```

### 4.4 環境変数の設定

#### ステップ1: .env.test ファイルの作成
```bash
nano .env.test
```

**内容** (APIキーは後で実際の値に置き換え):
```bash
ENVIRONMENT=test

# Public URL（AWS Lightsailの静的IPアドレス）
# ドメインがない場合: http://<静的IPアドレス>:8000
# ドメインがある場合: https://test-impact-db.your-domain.com
PUBLIC_BASE_URL=http://<静的IPアドレス>:8000

# OpenAI（後で実際の値に置き換え）
OPENAI_API_KEY=<SHARED_SEPARATELY>
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini

# Google Cloud（後で実際のパスに置き換え）
GOOGLE_APPLICATION_CREDENTIALS=~/impact_db/credentials/service-account.json

# Telegram Bots（後で実際の値に置き換え）
NARRATIVE_TELEGRAM_BOT_TOKEN=<SHARED_SEPARATELY>
NARRATIVE_TELEGRAM_SECRET_TOKEN=<SHARED_SEPARATELY>
IMPACT_TELEGRAM_BOT_TOKEN=<SHARED_SEPARATELY>
IMPACT_TELEGRAM_SECRET_TOKEN=<SHARED_SEPARATELY>

# Notion（後で実際の値に置き換え）
NOTION_API_KEY=<SHARED_SEPARATELY>
NOTION_ROOT_PAGE_ID=<SHARED_SEPARATELY>
NOTION_SCHOOLS_DB_ID=<SHARED_SEPARATELY>
NOTION_TEACHERS_DB_ID=<SHARED_SEPARATELY>
NOTION_NARRATIVES_DB_ID=<SHARED_SEPARATELY>
NOTION_SUBJECTS_DB_ID=<SHARED_SEPARATELY>
NOTION_STAFF_NARRATIVES_DB_ID=<SHARED_SEPARATELY>

# Settings
NARRATIVE_WINDOW_MINUTES=1
CATEGORY_MODE=hybrid
CHROMA_DIR=.chroma_categories
```

#### ステップ2: Google Cloud認証情報のアップロード
```bash
# ローカルマシンから
scp -i ~/Downloads/LightsailDefaultKey-ap-northeast-1.pem \
  /path/to/service-account.json \
  ubuntu@<静的IPアドレス>:~/impact_db/credentials/

# または、サーバー上で作成
mkdir -p ~/impact_db/credentials
nano ~/impact_db/credentials/service-account.json
# 内容を貼り付け
```

### 4.5 systemdサービスの作成

```bash
# サービスファイル作成
sudo nano /etc/systemd/system/impact_db.service
```

**内容**:
```ini
[Unit]
Description=Impact DB Test Environment
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/impact_db
Environment="ENVIRONMENT=test"
ExecStart=/home/ubuntu/impact_db/impact_db_env/bin/uvicorn project.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/var/log/impact_db/app.log
StandardError=append:/var/log/impact_db/error.log

[Install]
WantedBy=multi-user.target
```

**ログディレクトリ作成**:
```bash
sudo mkdir -p /var/log/impact_db
sudo chown ubuntu:ubuntu /var/log/impact_db
```

**サービス有効化と起動**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable impact_db
sudo systemctl start impact_db

# ステータス確認
sudo systemctl status impact_db

# ログ確認
sudo journalctl -u impact_db -f
```

### 4.6 ファイアウォール設定

> **Note**: AWS Lightsailでは、ファイアウォールはLightsailコンソールで管理します（ステップ4で設定済み）。
> Ubuntu上でUFWを使用する必要はありません。

Lightsailファイアウォールで既に以下を設定済み:
- SSH (TCP 22)
- Custom (TCP 8000) - FastAPIアプリケーション

### 4.7 Webhook設定

```bash
# ローカルマシンから実行
# 静的IPアドレスを使用する場合 (ドメインがない場合)
curl -X POST "https://api.telegram.org/bot<NARRATIVE_BOT_TOKEN>/setWebhook" \
  -d "url=http://<静的IPアドレス>:8000/telegram/narrative/webhook" \
  -d "secret_token=<SECRET_TOKEN>"

curl -X POST "https://api.telegram.org/bot<IMPACT_BOT_TOKEN>/setWebhook" \
  -d "url=http://<静的IPアドレス>:8000/telegram/impact/webhook" \
  -d "secret_token=<SECRET_TOKEN>"

# 確認
curl "https://api.telegram.org/bot<NARRATIVE_BOT_TOKEN>/getWebhookInfo"
```

> **セキュリティNote**: 本番環境ではHTTPSを使用することを強く推奨します。
> テスト環境では一時的にHTTPを使用していますが、本番環境ではドメイン + SSL証明書（Let's Encrypt等）を設定してください。

---

## 5. 第三者開発者へのアクセス権付与

### 5.1 Gitリポジトリへの招待

#### GitHub の場合:
1. リポジトリページ → "Settings" → "Collaborators"
2. "Add people"
3. 第三者開発者のGitHubアカウント名を入力
4. 権限: **Write**（Pull Request作成・コードプッシュ可能）

#### GitLab の場合:
1. プロジェクトページ → "Settings" → "Members"
2. "Invite member"
3. 権限: **Developer**

### 5.2 Notion読み取り専用アクセスの付与

#### ステップ1: 読み取り専用Integrationの作成
1. https://www.notion.so/my-integrations にアクセス
2. 「新しいインテグレーション」をクリック
3. 名前: "Impact DB Test (Read-Only)"
4. **権限設定**:
   - ✅ Read content
   - ❌ Update content
   - ❌ Insert content
5. 「送信」をクリック
6. **Internal Integration Token** をコピー

#### ステップ2: データベースを共有
1. 各テストデータベース（Schools, Teachers, Narratives等）を開く
2. 右上「⋯」→「Add connections」
3. 作成した「Impact DB Test (Read-Only)」を選択

#### ステップ3: APIキーを第三者開発者に共有
- **方法**: 1Password / Bitwarden の共有Vault
- **共有するキー**:
  ```
  NOTION_API_KEY_READ_ONLY=ntn_<read_only_integration_token>
  ```

### 5.3 API認証情報の共有

#### 共有する認証情報リスト:

| 認証情報 | 用途 | 共有方法 |
|---------|------|---------|
| **Telegram Bot Token** (Narrative) | テスト用Botへのアクセス | 1Password Vault |
| **Telegram Bot Token** (Impact) | テスト用Botへのアクセス | 1Password Vault |
| **Telegram Secret Token** (各2つ) | Webhook認証 | 1Password Vault |
| **Notion Read-Only API Key** | テストデータの読み取り | 1Password Vault |
| **Notion Database IDs** (全6つ) | DB接続 | 1Password Vault |
| **OpenAI API Key** | STT・LLM使用 | 1Password Vault |
| **Google Cloud Service Account JSON** | Google Cloud API | 個別にファイル送信 |

#### セキュアな共有手順:

**オプション1: 1Password / Bitwarden（推奨）**
1. 共有Vault「Impact DB Test Environment」を作成
2. 上記の認証情報をSecure Noteとして保存
3. 第三者開発者を Vault に招待

**オプション2: 暗号化ファイル**
1. `.env.test` ファイルを作成（実際の値を記載）
2. GPGで暗号化:
   ```bash
   gpg --symmetric --cipher-algo AES256 .env.test
   # パスワードを設定
   ```
3. 暗号化ファイル `.env.test.gpg` を送信
4. パスワードを別経路（電話・Signal等）で共有

**オプション3: Google Drive（最低限）**
1. Google Drive に専用フォルダ作成
2. アクセス権限: 「リンクを知っている特定のユーザー」
3. `.env.test` をアップロード
4. リンクを第三者開発者にメールで送信

### 5.4 テスト環境サーバーへのアクセス（任意）

**基本方針**: 通常は第三者開発者にサーバーアクセスを与えない

**もし必要な場合 (AWS Lightsail)**:

**オプション1: 既存のキーペアを共有**
```bash
# Lightsailダッシュボードからダウンロードした秘密鍵を共有
# LightsailDefaultKey-ap-northeast-1.pem
# → 1Password/Bitwardenで安全に共有
```

**オプション2: 新しいSSHキーを追加**
```bash
# プロジェクトオーナーがサーバー上で実行

# 第三者開発者のSSH公開鍵を受領
# authorized_keys に追加
echo "<developer-public-key>" | sudo tee -a /home/ubuntu/.ssh/authorized_keys
```

**推奨**: サーバーアクセスは最小限に。デプロイはプロジェクトオーナーが行う。

---

## 6. 開発ワークフロー

### 6.1 第三者開発者の開発手順

#### ステップ1: 環境セットアップ（初回のみ）
```bash
# リポジトリをクローン
git clone https://github.com/your-org/impact_db.git
cd impact_db

# Python仮想環境作成
python3 -m venv impact_db_env
source impact_db_env/bin/activate  # macOS/Linux
# または
impact_db_env\Scripts\activate     # Windows

# 依存関係インストール
pip install -r requirements.txt

# .env.test ファイルを作成
# 共有された認証情報を貼り付け
nano .env.test

# Google Cloud認証情報を配置
mkdir credentials
# service-account.json を credentials/ に配置
```

#### ステップ2: ローカルでの開発とテスト
```bash
# 環境変数を設定
export ENVIRONMENT=test

# ngrokで公開URL取得（Webhookテスト用）
ngrok http 8000
# または
cloudflared tunnel --url http://localhost:8000

# PUBLIC_BASE_URL を .env.test に設定
# PUBLIC_BASE_URL=https://abc123.ngrok.io

# Webhookを自分のngrok URLに設定
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://abc123.ngrok.io/telegram/narrative/webhook" \
  -d "secret_token=<SECRET_TOKEN>"

# アプリ起動
uvicorn project.main:app --host 0.0.0.0 --port 8000 --reload

# テスト用Telegramグループでメッセージ送信
# → ローカルサーバーが処理
```

#### ステップ3: 機能開発
```bash
# featureブランチを作成
git checkout -b feature/improve-audio-preprocessing

# コード変更
# ... 開発作業 ...

# コミット
git add .
git commit -m "Improve audio preprocessing pipeline"

# プッシュ
git push origin feature/improve-audio-preprocessing
```

#### ステップ4: Pull Request作成
1. GitHub/GitLab でPull Requestを作成
2. タイトル: 「Improve audio preprocessing pipeline」
3. 説明: 変更内容、テスト方法を記載
4. レビュワー: プロジェクトオーナーをアサイン

#### ステップ5: レビューと修正
1. プロジェクトオーナーがコードレビュー
2. 修正依頼があれば対応
3. 承認されたらマージ

#### ステップ6: テスト環境サーバーへのデプロイ（プロジェクトオーナーが実施）
```bash
# サーバーにSSH接続 (AWS Lightsail)
ssh -i ~/Downloads/LightsailDefaultKey-ap-northeast-1.pem ubuntu@<静的IPアドレス>

# 最新コードをプル
cd ~/impact_db
git pull origin main

# 依存関係更新（必要な場合）
source impact_db_env/bin/activate
pip install -r requirements.txt

# サービス再起動
sudo systemctl restart impact_db

# ログ確認
sudo journalctl -u impact_db -f
```

### 6.2 Git ブランチ戦略

```
main (サーバーにデプロイ)
  ├── develop (統合テスト用、オプション)
  │   ├── feature/improve-audio-preprocessing (開発者A)
  │   ├── feature/add-new-stt-engine (開発者B)
  │   └── bugfix/fix-notion-pagination (開発者C)
```

**ルール**:
- `main`: 保護ブランチ、PR必須
- `develop`: オプション（チームが小さければ不要）
- `feature/*`: 各開発者が自由に作成

---

## 7. セキュリティ対策

### 7.1 認証情報の保護

#### ✅ すべきこと:
- `.env.test` を `.gitignore` に追加（**必須**）
- 認証情報を1Password/Bitwardenで管理
- 定期的なAPIキーのローテーション（3〜6ヶ月ごと）
- アクセス権の定期的な見直し

#### ❌ してはいけないこと:
- `.env.test` をGitにコミット
- Slack/メールに平文で認証情報を送信
- GitHub Issue/Pull Requestに認証情報を記載

### 7.2 `.gitignore` の設定

**確認**: 以下が `.gitignore` に含まれているか

```gitignore
# Environment files
.env
.env.test
.env.production
.env.local

# Credentials
credentials/
*.json  # Google Cloud service account
service-account*.json

# Runtime
.chroma_categories/
.runtime/

# Python
__pycache__/
*.pyc
*.pyo
impact_db_env/

# Logs
logs/
*.log
```

### 7.3 アクセス権の管理

| 役割 | Gitリポジトリ | Notion | テスト環境サーバー | API Key |
|-----|-------------|--------|------------------|---------|
| **プロジェクトオーナー** | Admin | Full | SSH/FTP | All |
| **シニア開発者** | Write | Full | SSH (optional) | All |
| **第三者開発者** | Write | Read-Only | ❌ No Access | Read-Only (Notion) + Shared (Other) |

### 7.4 監査ログ

**推奨**: 以下の操作を記録
- Gitコミット履歴（自動）
- Notion API呼び出し（Notion側で自動記録）
- サーバーへのSSHログイン（`/var/log/auth.log`）
- APIキー使用量（OpenAI/Google Cloudダッシュボード）

---

## 8. トラブルシューティング

### 8.1 よくある問題

#### 問題1: 第三者開発者がローカルでWebhookを受信できない

**原因**: ngrokのURLがTelegramに設定されていない

**解決策**:
```bash
# ngrok起動
ngrok http 8000

# 表示されたHTTPS URLをコピー
# 例: https://abc123.ngrok.io

# Webhookを設定
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://abc123.ngrok.io/telegram/narrative/webhook" \
  -d "secret_token=<SECRET_TOKEN>"
```

#### 問題2: Notion APIが「Unauthorized」エラー

**原因**: Read-Only Integrationがデータベースと共有されていない

**解決策**:
1. Notionでデータベースを開く
2. 「⋯」→「Add connections」
3. 「Impact DB Test (Read-Only)」を選択

#### 問題3: サーバーでffmpegが使えない

**解決策**: 静的バイナリを使用
```bash
cd ~/impact_db
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar xf ffmpeg-release-amd64-static.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg ~/bin/
export PATH=$HOME/bin:$PATH
```

#### 問題4: systemdサービスが起動しない

**原因**: 環境変数やパスの問題

**解決策**:
```bash
# ログを確認
sudo journalctl -u impact_db -n 50

# サービスファイルを確認
sudo systemctl cat impact_db

# 手動で起動してエラーを確認
cd ~/impact_db
source impact_db_env/bin/activate
export ENVIRONMENT=test
uvicorn project.main:app --host 0.0.0.0 --port 8000
```

---

## 9. コスト見積もり

### 9.1 前提条件（カンボジアでの運用）

**利用パターン**:
- 50人/日 × 10リクエスト/人 = **500リクエスト/日**
- **15,000リクエスト/月** (30日換算)

**リクエストの内訳**:
- Narrative DB: 60% → 9,000リクエスト/月
  - テキスト処理 + 要約生成 (GPT-4o-mini)
  - Subject Tag分類 (GPT-4o-mini)
- Impact DB: 40% → 6,000リクエスト/月
  - 音声処理 (Whisper)
  - 翻訳 (Google Translate API)
  - カテゴライゼーション (text-embedding-3-small + GPT-4o-mini)

### 9.2 さくらのVPS vs AWS Lightsail 詳細比較

#### オプション1: さくらのVPS (1GBプラン) - カンボジアからのアクセス

**サーバーコスト**:
| 項目 | 料金 |
|-----|------|
| VPS (1GB) | ¥880/月 |
| **小計** | **¥880/月** |

**API使用コスト** (15,000リクエスト/月):

| サービス | 用途 | 月間使用量 | 単価 | 月額コスト |
|---------|------|-----------|------|----------|
| **OpenAI Whisper** | 音声→テキスト(6,000件) | 6,000分 (平均1分/件) | $0.006/分 | **$36** (¥5,256) |
| **OpenAI GPT-4o-mini** | 要約・分類・カテゴリ | 入力: 4.5M tokens<br>出力: 450k tokens | 入力: $0.15/1M<br>出力: $0.60/1M | **$0.95** (¥139) |
| **OpenAI Embeddings** | ベクトル化(6,000件) | 600k tokens | $0.02/1M tokens | **$0.01** (¥1) |
| **Google Translate** | クメール→英語(6,000件) | 600k文字 (平均100文字/件) | $20/1M文字 | **$12** (¥1,752) |
| **Google Cloud Storage** | 音声ファイル保存 | 5GB | $0.02/GB | **$0.10** (¥15) |
| **小計** | | | | **$49.06** (¥7,163) |

**ネットワーク遅延** (カンボジア → 日本):
- 平均レイテンシ: **60-80ms**
- 帯域幅: 安定 (さくらは国際回線も安定)

**合計コスト**:
```
サーバー:     ¥880
API:        ¥7,163
─────────────────
合計:       ¥8,043/月
```

---

#### オプション2: AWS Lightsail ($5プラン) - カンボジアからのアクセス

**サーバーコスト**:
| 項目 | 料金 |
|-----|------|
| Lightsail ($5プラン) | $5/月 (¥730) |
| データ転送 (1TB含む) | $0 (無料枠内) |
| **小計** | **$5/月 (¥730)** |

**API使用コスト** (15,000リクエスト/月):
- さくらのVPSと同じAPI使用量のため、**$49.06 (¥7,163)**

**ネットワーク遅延** (カンボジア → AWS東京リージョン):
- 平均レイテンシ: **40-60ms** ✅ さくらより高速
- 帯域幅: 非常に安定 (AWS Global Network)

**合計コスト**:
```
サーバー:     ¥730
API:        ¥7,163
─────────────────
合計:       ¥7,893/月
```

---

### 9.3 総合比較表

| 比較項目 | さくらのVPS | AWS Lightsail | 差額 |
|---------|-----------|--------------|------|
| **サーバー料金** | ¥880/月 | ¥730/月 | **Lightsail -¥150安い** |
| **API料金** | ¥7,163/月 | ¥7,163/月 | 同じ |
| **合計コスト** | **¥8,043/月** | **¥7,893/月** | **Lightsail -¥150安い** |
| **年間コスト** | ¥96,516 | ¥94,716 | **Lightsail -¥1,800安い** |
| | | | |
| **カンボジアからのレイテンシ** | 60-80ms | 40-60ms | **Lightsail 高速** |
| **日本語サポート** | ✅ あり | ❌ なし (英語のみ) | さくら有利 |
| **セットアップ難易度** | ⭐⭐☆☆☆ | ⭐⭐⭐☆☆ | さくら易しい |
| **拡張性** | 限定的 | 高い (AWS連携) | Lightsail有利 |
| **データ転送量制限** | 無制限 | 1TB/月 (超過時課金) | さくら有利 |
| **バックアップ** | 手動/スナップショット有料 | スナップショット有料 ($1/月) | ほぼ同じ |
| **モニタリング** | 基本的なもの | CloudWatch連携可能 | Lightsail有利 |

### 9.4 API コスト内訳詳細

#### OpenAI Whisper (音声→テキスト)
```
6,000リクエスト × 1分/リクエスト = 6,000分
6,000分 × $0.006/分 = $36/月 (¥5,256)
```

#### OpenAI GPT-4o-mini (要約・分類)
**入力トークン**:
- 要約生成 (9,000件): 9,000 × 400 tokens = 3,600k tokens
- Subject Tag分類 (9,000件): 9,000 × 50 tokens = 450k tokens
- カテゴリ分類 (6,000件): 6,000 × 75 tokens = 450k tokens
- **合計入力**: 4,500k tokens = 4.5M tokens

**出力トークン**:
- 要約生成 (9,000件): 9,000 × 40 tokens = 360k tokens
- Subject Tag分類 (9,000件): 9,000 × 5 tokens = 45k tokens
- カテゴリ分類 (6,000件): 6,000 × 10 tokens = 60k tokens
- **合計出力**: 465k tokens = 0.465M tokens

**コスト**:
```
入力: 4.5M × $0.15/1M = $0.675
出力: 0.465M × $0.60/1M = $0.279
合計: $0.95/月 (¥139)
```

#### Google Translate API
```
6,000件 × 100文字/件 = 600,000文字
600k × $20/1M文字 = $12/月 (¥1,752)
```

### 9.5 推奨判定

**コスト面**: AWS Lightsail **-¥150/月安い**（年間 -¥1,800）

**パフォーマンス面**: AWS Lightsail **20-40ms速い**（カンボジアから）

**運用面の総合判断**:

| 要素 | さくらのVPS | AWS Lightsail |
|-----|-----------|--------------|
| **日本語サポート** | ✅✅✅ 充実 | ❌ なし |
| **セットアップ難易度** | ✅✅ 易しい | ⚠️ やや難しい |
| **カンボジアからの速度** | ⚠️ 60-80ms | ✅✅ 40-60ms |
| **将来の拡張性** | ⚠️ 限定的 | ✅✅ AWSエコシステム |
| **コスト** | ⚠️ ¥8,043 | ✅ ¥7,893 |

---

### 9.6 最終推奨

#### 🥇 **AWS Lightsail を推奨**

**理由**:
1. **カンボジアからのアクセスが高速** (40-60ms vs 60-80ms)
2. **年間¥1,800安い**
3. **将来的な拡張性** (RDS、S3、CloudFront等と連携可能)
4. **グローバルで実績のあるインフラ**

**注意点**:
- セットアップが若干複雑 → この設計書で詳細手順を提供
- 日本語サポートなし → 英語ドキュメント + コミュニティ活用

#### 🥈 さくらのVPSが向いているケース:
- チームが英語に不慣れで日本語サポートが必須
- AWSアカウント作成が困難
- セットアップの簡易性を最優先

---

### 9.7 初期セットアップ時間

| タスク | 見積もり時間 |
|-------|-------------|
| サーバー契約・初期設定 | 1〜2時間 |
| Python環境・依存関係セットアップ | 1〜2時間 |
| systemdサービス設定 | 30分〜1時間 |
| Git・Notion・Telegram設定 | 2〜3時間 |
| 第三者開発者へのオンボーディング | 1〜2時間/人 |
| ドキュメント作成 | 3〜5時間 |
| **合計** | **8〜15時間** |

---

## 10. チェックリスト

### 10.1 プロジェクトオーナー側の準備

- [ ] **AWSアカウント作成**
- [ ] **AWS Lightsailインスタンス作成** ($5プラン, Tokyo, Ubuntu 22.04)
- [ ] **静的IPアドレスの割り当て**
- [ ] **ファイアウォール設定** (SSH, TCP 8000)
- [ ] **SSH接続確認** (秘密鍵ダウンロード)
- [ ] Pythonとffmpegのインストール
- [ ] Gitリポジトリの作成（プライベート）
- [ ] `.gitignore` の設定確認
- [ ] `.env.example` の作成
- [ ] Notion Read-Only Integrationの作成
- [ ] 1Password / Bitwardenの共有Vault作成
- [ ] 認証情報を共有Vaultに保存
- [ ] サーバーへのデプロイとsystemdサービス起動
- [ ] Webhookの設定 (HTTP + 静的IP)
- [ ] ヘルスチェック（`http://<静的IP>:8000/healthz`）

### 10.2 第三者開発者側の準備

- [ ] Gitリポジトリへのアクセス確認
- [ ] 1Password / Bitwarden Vaultへのアクセス確認
- [ ] ローカル環境のセットアップ
  - [ ] Python 3.9+ インストール
  - [ ] ffmpeg インストール
  - [ ] 仮想環境作成
  - [ ] 依存関係インストール
- [ ] `.env.test` ファイル作成
- [ ] Google Cloud認証情報の配置
- [ ] ngrok / Cloudflare Tunnel のインストール
- [ ] ローカルでの動作確認
- [ ] テスト用Telegramグループでのテスト
- [ ] Pull Requestの作成・プッシュテスト

---

## 11. 次のステップ

### 11.1 承認プロセス

1. **本文書のレビュー**: プロジェクトオーナーが確認
2. **決定事項の確認**:
   - ✅ **テスト環境サーバー**: AWS Lightsail ($5プラン)
   - ⚠️ **ドメイン**: 今回はHTTP + 静的IPで運用（本番環境ではHTTPS推奨）
   - ⚠️ **認証情報共有方法**: 1Password/Bitwarden/その他を決定
   - ⚠️ **第三者開発者へのSSHアクセス**: 必要性を判断
3. **予算承認**: 月額コスト **¥7,893** (サーバー¥730 + API¥7,163)
4. **スケジュール確認**: セットアップ開始日

### 11.2 実装タイムライン

| フェーズ | タスク | 期間 |
|---------|-------|------|
| **Day 1** | AWSアカウント作成・Lightsailインスタンス作成 | 半日 |
| **Day 1-2** | 静的IP割り当て・Python環境・systemd設定 | 1.5日 |
| **Day 3** | Git・Notion・Telegram設定 | 1日 |
| **Day 4** | 認証情報の整理と共有準備 | 1日 |
| **Day 5** | 第三者開発者オンボーディング | 1日 |

**合計見込み**: 5日（1週間以内）

---

## 12. 参考資料

### プロジェクト内ドキュメント
- [02_setup.md](02_setup.md) - セットアップガイド
- [03_architecture.md](03_architecture.md) - システムアーキテクチャ
- [07_troubleshooting.md](07_troubleshooting.md) - トラブルシューティング

### AWS Lightsail 公式ドキュメント
- AWS Lightsail 公式サイト: https://aws.amazon.com/lightsail/
- Lightsail ドキュメント: https://docs.aws.amazon.com/lightsail/
- Ubuntu on Lightsail: https://lightsail.aws.amazon.com/ls/docs/en_us/articles/amazon-lightsail-quick-start-guide-linux-unix

### その他参考資料
- Ubuntu公式: systemdサービス管理ガイド
- Telegram Bot API: https://core.telegram.org/bots/api
- FastAPI デプロイガイド: https://fastapi.tiangolo.com/deployment/

---

**文書終わり**

**次のアクション**: 本文書をレビューし、承認を得た後、セクション11.2のタイムラインに従って実装を開始する。
