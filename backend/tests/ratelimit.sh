#!/usr/bin/env bash
# 切磋會 登入 / 註冊限流驗證
#
# 注意：本腳本會把「當前來源 IP」打進限流名單
#   - 登入額度：10 次 / 60 秒
#   - 註冊額度：5 次 / 3600 秒
# 計數存在服務記憶體，跑完請重啟服務即可清除；否則該 IP 在視窗內無法登入 / 註冊。
#
# 用法：bash tests/ratelimit.sh [BASE_URL]
set -uo pipefail

BASE="${1:-http://127.0.0.1:8000}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LAST="$TMP/last.json"
HDR="$TMP/last.hdr"

PASS=0
FAIL=0
pass() { printf "  \033[32mPASS\033[0m  %s\n" "$1"; PASS=$((PASS + 1)); }
fail() { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAIL=$((FAIL + 1)); }
check() {
  if [ -z "$2" ]; then fail "$1 — 未取得值（期望 $3）"; return; fi
  [ "$2" = "$3" ] && pass "$1 ($2)" || fail "$1 — 期望 $3，實得 $2"
}

# post <路徑> <payload> -> 輸出狀態碼，回應標頭寫入 $HDR、本文寫入 $LAST
post() {
  curl -s -D "$HDR" -o "$LAST" -w '%{http_code}' \
    -X POST "$BASE$1" -H 'Content-Type: application/json' -d "$2"
}

BAD_LOGIN='{"email":"crosshair@example.com","password":"definitely-wrong"}'
GOOD_LOGIN='{"email":"crosshair@example.com","password":"demo-2026-agent"}'
# 格式錯誤的註冊請求：一樣會被計數，但不會真的建立帳號
BAD_REGISTER='{"email":"not-an-email","password":"whatever-1234","display_name":"測試"}'

echo "== 切磋會 限流驗證 =="
echo "目標：$BASE"
echo

echo "[1] 連續錯誤登入 12 次（門檻 10 次 / 60 秒）"
FIRST=""
LAST_CODE=""
for i in $(seq 1 12); do
  CODE="$(post /api/auth/login "$BAD_LOGIN")"
  [ "$i" -eq 1 ] && FIRST="$CODE"
  LAST_CODE="$CODE"
done
check "首次錯誤為 401" "$FIRST" "401"
check "第 12 次轉為 429" "$LAST_CODE" "429"
check "附帶 Retry-After 標頭" "$(grep -qi '^retry-after:' "$HDR" && echo yes || echo no)" "yes"
check "429 提示可讀" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["detail"][:4])' "$LAST")" "嘗試過於"

echo "[2] 額度用盡後的行為"
check "錯誤密碼仍被擋" "$(post /api/auth/login "$BAD_LOGIN")" "429"
check "正確密碼可通過（只累計失敗）" "$(post /api/auth/login "$GOOD_LOGIN")" "200"
check "成功登入後計數歸零" "$(post /api/auth/login "$BAD_LOGIN")" "401"

echo "[3] 註冊限流（門檻 5 次 / 3600 秒）"
CODES=""
for _ in $(seq 1 6); do
  CODES="$CODES $(post /api/auth/register "$BAD_REGISTER")"
done
check "前 5 次為 422" "$(echo "$CODES" | awk '{print $1, $2, $3, $4, $5}')" "422 422 422 422 422"
check "第 6 次轉為 429" "$(echo "$CODES" | awk '{print $6}')" "429"

echo
if [ "$FAIL" -eq 0 ]; then
  printf "\033[32m== 全部通過：%d / %d ==\033[0m\n" "$PASS" "$((PASS + FAIL))"
else
  printf "\033[31m== %d 通過 / %d 失敗 ==\033[0m\n" "$PASS" "$FAIL"
fi
echo "提醒：本 IP 額度已用盡，重啟服務即可清除。"
[ "$FAIL" -eq 0 ]
