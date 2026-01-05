# ファイアウォール設定作業ログ

**日付**: 2026-01-05
**作業者**: プロジェクトオーナー
**インスタンス名**: impact-narrative-db-test
**リージョン**: Singapore (ap-southeast-1)

---

## 作業概要

AWS Lightsailインスタンスのファイアウォール設定を実施し、必要なポートを開放しました。

---

## 作業手順

### 1. Lightsailダッシュボードにアクセス
- インスタンス `impact-narrative-db-test` を選択
- 「Networking」タブを選択

### 2. IPv4 Firewallルールの追加

以下のルールを追加しました:

| Application | Protocol | Port | 用途 |
|------------|----------|------|------|
| SSH | TCP | 22 | SSH接続（デフォルトで設定済み） |
| Custom | TCP | 8000 | FastAPI アプリケーション |
| HTTP | TCP | 80 | HTTP（将来のnginxリバースプロキシ用） |
| HTTPS | TCP | 443 | HTTPS（将来のSSL証明書用） |

---

## 設定結果

✅ SSH (TCP 22) - 設定済み
✅ Custom (TCP 8000) - 追加完了
✅ HTTP (TCP 80) - 追加完了
✅ HTTPS (TCP 443) - 追加完了

---

## 確認事項

- すべてのルールが正常に追加されていることを確認
- ファイアウォールステータスが「Active」であることを確認

---

## 次のステップ

- SSH接続してサーバーにログイン
- システムアップデートの実施
- Docker & Docker Composeのインストール

---

**ステータス**: ✅ 完了
**所要時間**: 約5分
