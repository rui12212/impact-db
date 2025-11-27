#!/usr/bin/env bash
set -euo pipefail
# 環境変数が空なら直ちにエラー
: "${NARRATIVE_TELEGRAM_BOT_TOKEN:?}"
: "${NARRATIVE_TELEGRAM_SECRET_TOKEN:?}"
: "${IMPACT_TELEGRAM_BOT_TOKEN:?}"
: "${IMPACT_TELEGRAM_SECRET_TOKEN:?}"
: "${PUBLIC_BASE_URL:?}"

source .env

# For Setting Webhook of Impact DB
curl -sS -X POST "https://api.telegram.org/bot${IMPACT_TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${PUBLIC_BASE_URL}/telegram/impact/webhook" \
  -d "secret_token=${IMPACT_TELEGRAM_SECRET_TOKEN}"
echo "Impact webhook set."

# For setting Webhook of Narrative DB
curl -sS -X POST "https://api.telegram.org/bot${NARRATIVE_TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${PUBLIC_BASE_URL}/telegram/narrative/webhook" \
  -d "secret_token=${NARRATIVE_TELEGRAM_SECRET_TOKEN}"

echo "Narrative webhook set."

# curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
#   -d "url=${PUBLIC_BASE_URL}/telegram/webhook" \
#   -d "secret_token=${TELEGRAM_SECRET_TOKEN}"
# echo
# echo "Webhook set to ${PUBLIC_BASE_URL}/telegram/webhook"
