#!/bin/bash
# 打印切磋會當前 Cloudflare 快速通道（quick tunnel）的外網地址。
# 快速通道每次（重）啟動域名都會變，這裡取日誌裡最後生成的那一個。
# 用法：scripts/quick-url.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$SCRIPT_DIR/../backend/logs/cloudflared-quick.log"

URL="$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1 || true)"

if [ -z "$URL" ]; then
  echo "還沒抓到外網地址。確認快速通道已啟動："
  echo "  launchctl print gui/$(id -u)/com.agentcommunity.cloudflared-quick | head -20"
  echo "日誌：$LOG"
  exit 1
fi

echo "$URL"
