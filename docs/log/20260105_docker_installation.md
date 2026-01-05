# Docker & Docker Compose インストール作業ログ

**日付**: 2026-01-05
**作業者**: プロジェクトオーナー
**インスタンス名**: impact-narrative-db-test
**リージョン**: Singapore (ap-southeast-1)
**OS**: Ubuntu 22.04 LTS

---

## 作業概要

AWS LightsailインスタンスにDocker Engine と Docker Compose Plugin をインストールしました。

---

## 作業手順

### 1. Dockerのインストール

#### Docker公式インストールスクリプトを使用

```bash
# インストールスクリプトのダウンロード
curl -fsSL https://get.docker.com -o get-docker.sh

# スクリプトの実行
sudo sh get-docker.sh
```

#### 実行結果
```
# Executing docker install script, commit: XXXXXX
+ sh -c apt-get update -qq >/dev/null
+ sh -c DEBIAN_FRONTEND=noninteractive apt-get install -y -qq apt-transport-https ca-certificates curl >/dev/null
+ sh -c install -m 0755 -d /etc/apt/keyrings
...
+ sh -c docker version
Client: Docker Engine - Community
 Version:           XX.X.X
 API version:       X.XX
 Go version:        goX.XX.X
 Git commit:        XXXXXXX
 Built:             ...
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          XX.X.X
  API version:      X.XX (minimum version X.XX)
  Go version:       goX.XX.X
  Git commit:       XXXXXXX
  Built:            ...
  OS/Arch:          linux/amd64
  ...

================================================================================

To run Docker as a non-privileged user, consider setting up the
Docker daemon in rootless mode for your user:

    dockerd-rootless-setuptool.sh install

Visit https://docs.docker.com/go/rootless/ to learn about rootless mode.


To run the Docker daemon as a fully privileged service, but granting non-root
users access, refer to https://docs.docker.com/go/daemon-access/

WARNING: Access to the remote API on a privileged Docker daemon is equivalent
         to root access on the host. Refer to the 'Docker daemon attack surface'
         documentation for details: https://docs.docker.com/go/attack-surface/

================================================================================
```

---

### 2. ubuntuユーザーをdockerグループに追加

```bash
# dockerグループに追加
sudo usermod -aG docker ubuntu

# 設定を反映させるためログアウト
exit
```

---

### 3. 再ログインして権限確認

再度SSH接続後:

```bash
# dockerコマンドがsudoなしで実行できることを確認
docker --version
```

#### 結果
```
Docker version XX.X.X, build XXXXXXX
```

---

### 4. Docker Compose Pluginのインストール

```bash
# Docker Compose Pluginのインストール
sudo apt install docker-compose-plugin -y
```

#### 実行結果
```
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
The following additional packages will be installed:
  docker-buildx-plugin
The following NEW packages will be installed:
  docker-buildx-plugin docker-compose-plugin
0 upgraded, 2 newly installed, 0 to remove and 0 not upgraded.
Need to get XX MB of archives.
After this operation, XX MB of additional disk space will be used.
Do you want to continue? [Y/n] Y
...
Setting up docker-compose-plugin (X.XX.X-X~ubuntu.XX.XX~jammy) ...
...
```

---

### 5. バージョン確認

```bash
# Docker バージョン
docker --version

# Docker Compose バージョン
docker compose version
```

#### 結果
```
Docker version XX.X.X, build XXXXXXX
Docker Compose version vX.XX.X
```

---

### 6. Gitのインストール確認

```bash
# Gitバージョン確認（通常プリインストール済み）
git --version
```

#### 結果
```
git version X.XX.X
```

---

## 動作確認

### Docker Engineの動作確認

```bash
# Hello Worldコンテナの実行
docker run hello-world
```

#### 結果
```
Unable to find image 'hello-world:latest' locally
latest: Pulling from library/hello-world
...
Status: Downloaded newer image for hello-world:latest

Hello from Docker!
This message shows that your installation appears to be working correctly.
...
```

---

## インストール済みソフトウェア一覧

| ソフトウェア | バージョン | 用途 |
|------------|---------|------|
| Docker Engine | XX.X.X | コンテナランタイム |
| Docker Compose Plugin | vX.XX.X | マルチコンテナ管理 |
| Git | X.XX.X | バージョン管理 |

---

## トラブルシューティング

### 問題: dockerコマンドが"permission denied"エラー

**原因**: ubuntuユーザーがdockerグループに追加されていない、または再ログインしていない

**解決策**:
```bash
# dockerグループに追加
sudo usermod -aG docker ubuntu

# ログアウト & 再ログイン
exit
# 再度SSH接続
```

---

## 次のステップ

- Dockerfile の作成（ローカルで作成）
- docker-compose.yml の作成（ローカルで作成）
- .dockerignore の作成（ローカルで作成）
- プロジェクトをGitリポジトリからクローン

---

**ステータス**: ✅ 完了
**所要時間**: 約10-15分
