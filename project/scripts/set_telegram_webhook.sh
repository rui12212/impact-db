#!/usr/bin/env bash
set -euo pipefail
# 環境変数が空なら直ちにエラー
: "${TELEGRAM_BOT_TOKEN:?}"
: "${TELEGRAM_SECRET_TOKEN:?}"
: "${PUBLIC_BASE_URL:?}"

curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${PUBLIC_BASE_URL}/telegram/webhook" \
  -d "secret_token=${TELEGRAM_SECRET_TOKEN}"
echo
echo "Webhook set to ${PUBLIC_BASE_URL}/telegram/webhook"
