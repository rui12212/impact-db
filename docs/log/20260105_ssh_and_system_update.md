# SSH接続とシステムアップデート作業ログ

**日付**: 2026-01-05
**作業者**: プロジェクトオーナー
**インスタンス名**: impact-narrative-db-test
**リージョン**: Singapore (ap-southeast-1)
**OS**: Ubuntu 22.04 LTS

---

## 作業概要

AWS LightsailインスタンスにSSH接続し、システムアップデートを実施しました。

---

## 作業手順

### 1. SSH接続

#### 方法1: ブラウザSSH（使用した方法）
1. Lightsailダッシュボードで `impact-narrative-db-test` を選択
2. 「Connect」タブをクリック
3. 「Connect using SSH」ボタンをクリック
4. ブラウザ上でSSHターミナルが起動

#### 方法2: ローカルターミナルからの接続（参考）
```bash
# 秘密鍵をダウンロード
# Lightsail → Account → SSH keys → Download

# パーミッション設定
chmod 400 ~/Downloads/LightsailDefaultKey-ap-southeast-1.pem

# SSH接続
ssh -i ~/Downloads/LightsailDefaultKey-ap-southeast-1.pem ubuntu@<静的IPアドレス>
```

---

### 2. システムアップデート

接続後、以下のコマンドを実行:

```bash
# パッケージリストの更新
sudo apt update

# インストール済みパッケージのアップグレード
sudo apt upgrade -y
```

---

## 実行結果

### apt update の結果
```
Hit:1 http://ap-southeast-1.ec2.archive.ubuntu.com/ubuntu jammy InRelease
Get:2 http://ap-southeast-1.ec2.archive.ubuntu.com/ubuntu jammy-updates InRelease
Get:3 http://ap-southeast-1.ec2.archive.ubuntu.com/ubuntu jammy-backports InRelease
Get:4 http://security.ubuntu.com/ubuntu jammy-security InRelease
Fetched X kB in Xs
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
XX packages can be upgraded. Run 'apt list --upgradable' to see them.
```

### apt upgrade の結果
```
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Calculating upgrade... Done
The following packages will be upgraded:
  [アップグレードされたパッケージのリスト]
XX upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Need to get XX MB of archives.
After this operation, XX kB disk space will be freed.
Do you want to continue? [Y/n] Y
...
Processing triggers for...
...
Done.
```

---

## 確認事項

### システム情報
```bash
# OS バージョン確認
cat /etc/os-release
# PRETTY_NAME="Ubuntu 22.04.X LTS"

# カーネルバージョン確認
uname -r
# 5.15.0-XXX-generic

# ディスク使用状況
df -h
# /dev/xvda1       40G   XX.XG  XX.XG  XX% /
```

---

## トラブルシューティング

特に問題は発生しませんでした。

---

## 次のステップ

- Docker & Docker Composeのインストール
- Gitの確認（通常プリインストール済み）

---

**ステータス**: ✅ 完了
**所要時間**: 約5-10分（アップデートの量による）
