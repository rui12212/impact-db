#!/usr/bin/env bash
#
# cron から呼ぶバッチの入口。
#
#   docker/run-batch.sh daily
#   docker/run-batch.sh weekly
#   docker/run-batch.sh weekly --job ai_summary
#
# cron の落とし穴を4つ吸収する:
#
#   ① cronにはTTYが無い        → docker compose exec に -T を付ける
#                                 付けないと "the input device is not a TTY"
#   ② cronのPATHは /usr/bin:/bin だけ
#                              → docker を絶対パスで探す。compose も絶対パス
#   ③ 週1のジョブは30分かかる  → mkdir の鍵で二重実行を防ぐ。
#                                 同じブロックを2つのプロセスが書き換えると
#                                 トグルの箇条書きが二重になる等、壊れ方が読めない
#   ④ コンテナが落ちていると失敗 → 先に確認して「何をすればいいか」を1行で出す。
#                                 "service app is not running" だけだと
#                                 何週間も見過ごされる
#
# 終了コード: バッチの終了コードをそのまま返す（1つでも失敗なら1）。
# cron がメールやアラートを出せるようにするため。

set -uo pipefail

# ---- 設定 ------------------------------------------------------------
# このスクリプトの場所から repo のルートを決める。
# cron は cd した状態で動かないので、相対パスに頼れない
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"

# 本番では IMPACT_COMPOSE_FILE で v2.prod.yml を指す
COMPOSE_FILE="${IMPACT_COMPOSE_FILE:-${HERE}/v2.local.yml}"
SERVICE="app"
LOG_DIR="${IMPACT_LOG_DIR:-${REPO}/.runtime/logs}"

# ② docker の場所。インストール方法で変わるので実際にある場所を探す
DOCKER="$(command -v docker || true)"
for candidate in /usr/bin/docker /usr/local/bin/docker /snap/bin/docker; do
    [ -n "${DOCKER}" ] && break
    [ -x "${candidate}" ] && DOCKER="${candidate}"
done

# ---- 引数 ------------------------------------------------------------
if [ $# -lt 1 ]; then
    echo "使い方: $0 {daily|weekly|all} [--job NAME]" >&2
    exit 2
fi
SCHEDULE="$1"
shift

case "${SCHEDULE}" in
    daily|weekly|all) ;;
    *) echo "不明なスケジュール: ${SCHEDULE}" >&2; exit 2 ;;
esac

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/batch-${SCHEDULE}.log"
LOCK_DIR="/tmp/impact-batch-${SCHEDULE}.lock"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" | tee -a "${LOG_FILE}"
}

# ---- 事前確認 --------------------------------------------------------
if [ -z "${DOCKER}" ]; then
    log "NG docker が見つからない。PATH=${PATH}"
    exit 1
fi

if [ ! -f "${COMPOSE_FILE}" ]; then
    log "NG compose ファイルが無い: ${COMPOSE_FILE}"
    exit 1
fi

# ④ コンテナが動いていないと exec は失敗する。先に分かる形で止める
if ! "${DOCKER}" compose -f "${COMPOSE_FILE}" ps --status running \
        --format '{{.Service}}' 2>/dev/null | grep -qx "${SERVICE}"; then
    log "NG コンテナ ${SERVICE} が動いていない。先に下記を実行してください"
    log "   ${DOCKER} compose -f ${COMPOSE_FILE} up -d"
    exit 1
fi

# ---- 鍵を取る --------------------------------------------------------
# ③ 二重実行を防ぐ。
#
# flock は Linux 専用（macOSに無い）ので mkdir で鍵を作る。
# mkdir は「既にあれば失敗する」が原子的に保証されるので鍵として使える。
# 待たずに諦める。待つとプロセスが溜まる。週1なら次回に任せる方が安全
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    OWNER=""
    [ -f "${LOCK_DIR}/pid" ] && OWNER="$(cat "${LOCK_DIR}/pid" 2>/dev/null)"

    if [ -n "${OWNER}" ] && kill -0 "${OWNER}" 2>/dev/null; then
        log "SKIP 前回の ${SCHEDULE} がまだ動いている (pid=${OWNER})"
        exit 0
    fi

    # プロセスが死んでいる = 前回が異常終了して鍵が残った
    log "WARN 残っていた鍵を掃除する (pid=${OWNER:-不明})"
    rm -rf "${LOCK_DIR}"
    if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
        log "NG 鍵を作れない: ${LOCK_DIR}"
        exit 1
    fi
fi

echo "$$" > "${LOCK_DIR}/pid"
# 正常終了・異常終了・Ctrl-C のどれでも鍵を返す
trap 'rm -rf "${LOCK_DIR}"' EXIT

# ---- 実行 ------------------------------------------------------------

log "START ${SCHEDULE} $*"
START=$(date +%s)

# ① -T: TTYを割り当てない。cron には TTY が無いので必須
"${DOCKER}" compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" \
    python -m v2_app.batch.runner "${SCHEDULE}" "$@" >>"${LOG_FILE}" 2>&1
CODE=$?

ELAPSED=$(( $(date +%s) - START ))
if [ ${CODE} -eq 0 ]; then
    log "DONE ${SCHEDULE} (${ELAPSED}秒)"
else
    log "FAIL ${SCHEDULE} 終了コード=${CODE} (${ELAPSED}秒)"
fi

exit ${CODE}
