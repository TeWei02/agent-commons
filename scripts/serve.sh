#!/usr/bin/env bash
# 切磋會 正式啟動腳本（單 worker）
#
# 用法：
#   bash scripts/serve.sh                 # 只監聽本機 127.0.0.1:8000
#   AC_HOST=0.0.0.0 bash scripts/serve.sh # 開放同網段裝置連入
#
# 環境變數可由 backend/.env 提供，或在命令前綴覆寫。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
cd "$BACKEND"

# 載入 .env（若存在）
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PY="$BACKEND/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "找不到虛擬環境：$BACKEND/.venv" >&2
  echo "請先執行：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

HOST="${AC_HOST:-127.0.0.1}"
PORT="${AC_PORT:-8000}"
# SQLite 寫入是單檔鎖，worker 開多反而更容易互鎖；小社群 1 個就夠
WORKERS="${AC_WORKERS:-1}"

echo "切磋會啟動：http://${HOST}:${PORT}  (workers=${WORKERS}, secure_cookie=${AC_COOKIE_SECURE:-0})"

# --proxy-headers：置於 Cloudflare / nginx 後方時，正確還原來源 IP 與 HTTPS 判定
exec "$PY" -m uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$WORKERS" \
  --proxy-headers \
  --forwarded-allow-ips='*'
