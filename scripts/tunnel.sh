#!/usr/bin/env bash
# 用 Cloudflare 快速通道（Quick Tunnel）把本機服務開到公網
#
# 特性：免註冊、免網域、自動配發 https 網址。
# 限制：網址是隨機的、每次重啟都會換，且 Cloudflare 不保證可用性；
#       適合小社群試營運。要固定網址請改用「具名通道 + 自有網域」。
#
# 用法：
#   bash scripts/tunnel.sh                       # 轉發 127.0.0.1:8000
#   AC_LOCAL_URL=http://127.0.0.1:9000 bash scripts/tunnel.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/bin"
URL="${AC_LOCAL_URL:-http://127.0.0.1:8000}"

# 優先用系統既有的 cloudflared；沒有才下載到專案 bin/（不動系統目錄）
if command -v cloudflared >/dev/null 2>&1; then
  CF="$(command -v cloudflared)"
  echo "使用系統既有的 cloudflared：${CF}"
else
  CF="${BIN_DIR}/cloudflared"
  if [ ! -x "${CF}" ]; then
    echo "首次執行：下載 cloudflared（約 40MB，存於 ${BIN_DIR}）"
    mkdir -p "${BIN_DIR}"
    case "$(uname -m)" in
      arm64) ASSET="cloudflared-darwin-arm64.tgz" ;;
      x86_64) ASSET="cloudflared-darwin-amd64.tgz" ;;
      *) echo "不支援的 CPU 架構：$(uname -m)" >&2; exit 1 ;;
    esac
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${ASSET}" -o "${BIN_DIR}/cf.tgz"
    tar -xzf "${BIN_DIR}/cf.tgz" -C "${BIN_DIR}"
    rm -f "${BIN_DIR}/cf.tgz"
    chmod +x "${CF}"
  fi
fi

echo "正在為 $URL 開啟公網通道…"
echo "（啟動後畫面上會出現一條 https://<隨機名稱>.trycloudflare.com 網址，複製給朋友即可）"
echo

exec "$CF" tunnel --url "$URL" --no-autoupdate
