"""開発用Botの webhook を、手元のトンネルのURLに貼り替える。

  docker compose -f docker/v2.local.yml up -d
  python project/v2_app/scripts/dev_webhook.py

  # いま貼ってある先を見るだけ
  python project/v2_app/scripts/dev_webhook.py --info

  # 開発Botの webhook を外す（getUpdates で試したい時など）
  python project/v2_app/scripts/dev_webhook.py --delete

**手元で動かす。** コンテナの中からは docker のログを読めないため。
標準ライブラリだけで動く（pip install は不要）。

仕組み:
  ① cloudflared（tunnel サービス）のログから公開URLを取る
  ② env/v2.dev.env のトークンで setWebhook を叩く
  ③ getWebhookInfo で貼れたか確認する

⚠️ **本番のBotを触らないための防御が2つ入っている。**
   1. 読む env ファイルは **env/v2.dev.env だけ**（本番は読まない）
   2. トークンが env/v2.prod.env のものと一致したら**中断する**
      （dev の env に本番のトークンが残っていると本番が止まる）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_ENV = REPO_ROOT / "env" / "v2.dev.env"
PROD_ENV = REPO_ROOT / "env" / "v2.prod.env"
COMPOSE = REPO_ROOT / "docker" / "v2.local.yml"

WEBHOOK_PATH = "/telegram/v2/webhook"
TUNNEL_SERVICE = "tunnel"
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def read_env(path: Path) -> Dict[str, str]:
    """env ファイルを読む。python-dotenv を使わない（依存を増やさない）。"""
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def tunnel_url() -> Optional[str]:
    """cloudflared のログから公開URLを取る。

    クイックトンネルはURLをログに出すだけで、APIが無い。
    """
    try:
        res = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), "logs", TUNNEL_SERVICE],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        print(f"docker compose logs に失敗: {e}")
        return None

    found = URL_PATTERN.findall(res.stdout + res.stderr)
    if not found:
        return None
    # 再起動していると複数出る。**最後のものが今のURL**
    return found[-1]


def call(token: str, method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def show_info(token: str) -> int:
    info = call(token, "getWebhookInfo").get("result", {})
    print("現在の webhook:")
    print(f"  URL            : {info.get('url') or '（未設定）'}")
    print(f"  保留中のupdate : {info.get('pending_update_count')}")
    if info.get("last_error_message"):
        print(f"  ⚠️ 直近のエラー : {info['last_error_message']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--info", action="store_true", help="貼ってある先を見るだけ")
    parser.add_argument("--delete", action="store_true", help="webhook を外す")
    args = parser.parse_args()

    dev = read_env(DEV_ENV)
    token = dev.get("V2_TELEGRAM_BOT_TOKEN", "")
    secret = dev.get("V2_TELEGRAM_SECRET_TOKEN", "")

    if not token:
        print(f"V2_TELEGRAM_BOT_TOKEN が {DEV_ENV} にありません")
        return 1

    # ⚠️ 本番のBotを触らない。dev に本番のトークンが残っていたら止める
    prod_token = read_env(PROD_ENV).get("V2_TELEGRAM_BOT_TOKEN", "")
    if prod_token and token == prod_token:
        print("⚠️ 中断しました。")
        print(f"   {DEV_ENV.name} のトークンが **本番と同じ** です。")
        print("   このまま実行すると本番Botの webhook が手元に向き、")
        print("   先生からのメッセージが届かなくなります。")
        print()
        print("   BotFather で開発用Botを作り、トークンを差し替えてください。")
        return 1

    me = call(token, "getMe").get("result", {})
    if not me:
        print("トークンが無効です（getMe が返りませんでした）")
        return 1
    print(f"Bot: @{me.get('username')}（{me.get('first_name')}）")

    if args.info:
        return show_info(token)

    if args.delete:
        res = call(token, "deleteWebhook", drop_pending_updates="false")
        print("削除:", "成功" if res.get("ok") else res)
        return 0 if res.get("ok") else 1

    url = tunnel_url()
    if not url:
        print("トンネルのURLが見つかりません。")
        print("  docker compose -f docker/v2.local.yml up -d")
        print("  で tunnel サービスを起動し、10秒ほど待ってから再実行してください。")
        return 1

    target = url + WEBHOOK_PATH
    print(f"貼り先: {target}")

    params = {
        "url": target,
        "allowed_updates": json.dumps(["message", "callback_query"]),
        # ⚠️ 開発では捨ててよい。本番のスクリプトと違う判断
        "drop_pending_updates": "true",
    }
    if secret:
        params["secret_token"] = secret

    res = call(token, "setWebhook", **params)
    if not res.get("ok"):
        print("失敗:", res.get("description"))
        return 1

    print("登録しました\n")
    return show_info(token)


if __name__ == "__main__":
    sys.exit(main())
