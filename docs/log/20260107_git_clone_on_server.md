# サーバーでのGitリポジトリクローン作業ログ

**日付**: 2026-01-07
**作業者**: プロジェクトオーナー
**サーバー**: AWS Lightsail impact-narrative-db-test (Singapore)
**OS**: Ubuntu 22.04 LTS

---

## 作業概要

AWS LightsailサーバーにSSH鍵を設定し、GitHubからimpact_dbリポジトリをクローンしました。

---

## 作業手順

### 1. サーバーにSSH接続

#### ブラウザSSH（推奨）
```
Lightsailダッシュボード → impact-narrative-db-test → Connect → Connect using SSH
```

#### またはローカルターミナルから
```bash
ssh -i ~/Downloads/LightsailDefaultKey-ap-southeast-1.pem ubuntu@<静的IPアドレス>
```

---

### 2. GitHub用SSH鍵の生成

```bash
# ホームディレクトリに移動
cd ~

# SSH鍵ペアを生成
ssh-keygen -t ed25519 -C "ubuntu@impact-narrative-db-test"
```

**実行結果**:
```
Generating public/private ed25519 key pair.
Enter file in which to save the key (/home/ubuntu/.ssh/id_ed25519): [Enter]
Enter passphrase (empty for no passphrase): [Enter]
Enter same passphrase again: [Enter]
Your identification has been saved in /home/ubuntu/.ssh/id_ed25519
Your public key has been saved in /home/ubuntu/.ssh/id_ed25519.pub
The key fingerprint is:
SHA256:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX ubuntu@impact-narrative-db-test
```

---

### 3. 公開鍵の確認と取得

```bash
# 公開鍵を表示
cat ~/.ssh/id_ed25519.pub
```

**出力例**:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx ubuntu@impact-narrative-db-test
```

この公開鍵をコピーしました。

---

### 4. GitHubにSSH鍵を登録

1. GitHub.com にログイン
2. 右上プロフィールアイコン → **Settings**
3. 左メニュー → **SSH and GPG keys**
4. **New SSH key** ボタンをクリック
5. 登録内容:
   - **Title**: `impact-narrative-db-test (AWS Lightsail)`
   - **Key**: コピーした公開鍵を貼り付け
6. **Add SSH key** をクリック

---

### 5. GitHub接続テスト

```bash
# SSH接続テスト
ssh -T git@github.com
```

**成功時の出力**:
```
Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.
```

✅ 認証成功を確認

---

### 6. リポジトリのクローン

```bash
# ホームディレクトリに移動
cd ~

# リポジトリをクローン
git clone git@github.com:<username>/impact_db.git

# プロジェクトディレクトリに移動
cd impact_db
```

**クローン結果**:
```
Cloning into 'impact_db'...
remote: Enumerating objects: XXX, done.
remote: Counting objects: 100% (XXX/XXX), done.
remote: Compressing objects: 100% (XXX/XXX), done.
remote: Total XXX (delta XXX), reused XXX (delta XXX), pack-reused 0
Receiving objects: 100% (XXX/XXX), XX.XX MiB | XX.XX MiB/s, done.
Resolving deltas: 100% (XXX/XXX), done.
```

---

### 7. ブランチの切り替え

```bash
# リモートブランチを確認
git branch -a

# feature/create_docker_environmentブランチに切り替え
git checkout feature/create_docker_environment
```

**出力**:
```
Branch 'feature/create_docker_environment' set up to track remote branch 'feature/create_docker_environment' from 'origin'.
Switched to a new branch 'feature/create_docker_environment'
```

---

### 8. Dockerファイルの確認

```bash
# Dockerファイルが存在するか確認
ls -la Dockerfile docker-compose.yml .dockerignore
```

**確認結果**:
```
-rw-rw-r-- 1 ubuntu ubuntu  564 Jan  7 XX:XX .dockerignore
-rw-rw-r-- 1 ubuntu ubuntu  811 Jan  7 XX:XX Dockerfile
-rw-rw-r-- 1 ubuntu ubuntu  830 Jan  7 XX:XX docker-compose.yml
```

✅ すべてのDockerファイルが正常にクローンされていることを確認

---

### 9. プロジェクト構造の確認

```bash
# ディレクトリ構造を確認
tree -L 2 -a
# または
ls -la
```

**主要ファイル・ディレクトリ**:
- ✅ `Dockerfile`
- ✅ `docker-compose.yml`
- ✅ `.dockerignore`
- ✅ `requirements.txt`
- ✅ `project/` (アプリケーションコード)
- ✅ `docs/` (ドキュメント)
- ⚠️ `.env.test` (未作成 - 次のステップで作成)
- ⚠️ `credentials/` (未作成 - 次のステップで作成)

---

## 確認事項

### Git設定
```bash
# 現在のブランチ確認
git branch
# * feature/create_docker_environment

# 最新コミット確認
git log --oneline -3
# 17b7d30c create_Dockerfile_and_docker_compose
# 88864800 making_ducumentation_and_setting_aws_lightsail
# 3db292bb add api services
```

### ディスク使用量
```bash
# プロジェクトサイズ確認
du -sh ~/impact_db
# 約XX MB
```

---

## トラブルシューティング

### 問題: SSH接続がタイムアウト

**解決策**:
```bash
# SSH設定を編集
nano ~/.ssh/config

# 以下を追加
Host github.com
  ServerAliveInterval 60
  ServerAliveCountMax 10
```

### 問題: Permission denied (publickey)

**原因**: SSH鍵がGitHubに登録されていない、または間違った鍵を使用している

**解決策**:
```bash
# 公開鍵を再確認
cat ~/.ssh/id_ed25519.pub
# GitHubに登録されている鍵と一致するか確認
```

---

## 次のステップ

- [ ] `.env.test` ファイルの作成
- [ ] Google Cloud認証情報のアップロード
- [ ] 必要なディレクトリの作成 (`.chroma_categories`, `.runtime`, `credentials`)
- [ ] Dockerイメージのビルド
- [ ] Dockerコンテナの起動

---

**ステータス**: ✅ 完了
**所要時間**: 約10-15分
