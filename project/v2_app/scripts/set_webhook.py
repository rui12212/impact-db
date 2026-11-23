"""TelegramのwebhookをV2のURLに向ける。

  # 登録
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/set_webhook.py https://xxxx.ngrok-free.app

  # 今の状態を見る
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/set_webhook.py --info

  # 外す（ngrokを止める前に実行しておくと、Telegramが再送を続けない）
  docker compose -f docker/v2.local.yml exec app \
      python project/v2_app/scripts/set_webhook.py --delete

⚠️ 無料プランのngrokはURLが起動ごとに変わる。
   ngrokを再起動したら、新しいURLでもう一度これを実行する。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from v2_app.core import telegram
from v2_app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_SECRET_TOKEN

PATH = "/telegram/v2/webhook"


def _check_env() -> int:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("V2_TELEGRAM_BOT_TOKEN（BotFatherが発行）")
    if not TELEGRAM_SECRET_TOKEN:
        missing.append("V2_TELEGRAM_SECRET_TOKEN（自分で決める）")
    if missing:
        print("env/v2.local.env に足りないものがあります:")
        for m in missing:
            print(f"  {m}")
        print("\n入れたら作り直しが必要です:")
        print("  docker compose -f docker/v2.local.yml up -d --force-recreate app")
        return 1
    return 0


def _print_info(info: dict) -> None:
    print(f"  URL            : {info.get('url') or '(未設定)'}")
    print(f"  保留中のupdate : {info.get('pending_update_count', 0)}")
    allowed = info.get("allowed_updates")
    print(f"  受け取る種類   : {allowed or '(既定=ほぼ全部)'}")

    # 直近のエラーが入っていれば、ほぼこれが原因
    if info.get("last_error_message"):
        print(f"\n  ⚠️ 直近のエラー : {info['last_error_message']}")
        print(f"     発生時刻     : {info.get('last_error_date')}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "base_url",
        nargs="?",
        help="ngrok などの https URL（例: https://xxxx.ngrok-free.app）",
    )
    parser.add_argument("--info", action="store_true", help="今の状態を見る")
    parser.add_argument("--delete", action="store_true", help="webhookを外す")
    args = parser.parse_args()

    if _check_env():
        return 1

    if args.info:
        print("現在の webhook:")
        _print_info(await telegram.get_webhook_info())
        return 0

    if args.delete:
        await telegram.delete_webhook()
        print("webhook を外しました")
        return 0

    if not args.base_url:
        parser.print_help()
        return 2

    base = args.base_url.rstrip("/")
    if not base.startswith("https://"):
        # TelegramはHTTPSしか受け付けない
        print(f"httpsで始まるURLが必要です: {base}")
        return 1

    url = base + PATH
    await telegram.set_webhook(url, TELEGRAM_SECRET_TOKEN)
    print(f"登録しました: {url}")

    print("\n登録後の状態:")
    _print_info(await telegram.get_webhook_info())

    print("\nBotに /start と送ってみてください。ログはこちら:")
    print("  docker compose -f docker/v2.local.yml logs -f app")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
