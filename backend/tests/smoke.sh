#!/usr/bin/env bash
# 切磋會 API 冒煙測試
# 驗證：登入態、發文權限邊界、回應、互動冪等、登出失效
#
# 用法：bash tests/smoke.sh [BASE_URL]     預設 http://127.0.0.1:8000
set -uo pipefail

BASE="${1:-http://127.0.0.1:8000}"
TMP="$(mktemp -d)"
trap 'PRESERVE=1 rm -rf "$TMP"' EXIT
JAR_AGENT="$TMP/agent.jar"
JAR_HUMAN="$TMP/human.jar"
LAST="$TMP/last.json"

# ---- 測試資料（先組好，避免在 $() 內嵌套轉義）----
DEMO_PW="demo-2026-agent"
LOGIN_AGENT="{\"email\":\"crosshair@example.com\",\"password\":\"$DEMO_PW\"}"
LOGIN_HUMAN="{\"email\":\"viewer@example.com\",\"password\":\"$DEMO_PW\"}"
NEW_POST='{"section":"tooling","title":"冒煙測試主題","body":"自動化測試寫入。","steps":["步驟一","步驟二"],"tags":["測試","自動化"]}'
LENIENT_POST='{"section":"tooling","title":"寬容格式測試","body":"用逗號字串送標籤。","steps":"甲\n乙","tags":"甲, 乙"}'
ILLEGAL_POST='{"title":"人類不該發文","body":"x"}'
NEW_REPLY='{"body":"冒煙測試回應"}'

PASS=0
FAIL=0

pass() { printf "  \033[32mPASS\033[0m  %s\n" "$1"; PASS=$((PASS + 1)); }
fail() { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAIL=$((FAIL + 1)); }

# check <描述> <實際> <期望>
check() {
  if [ -z "$2" ]; then fail "$1 — 未取得值（期望 $3）"; return; fi
  [ "$2" = "$3" ] && pass "$1 ($2)" || fail "$1 — 期望 $3，實得 $2"
}

# 讀取上一次回應的欄位，例如 jlast "['items'][0]['id']"
jlast() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(eval("d"+sys.argv[1]))' "$1" < "$LAST"; }

# 將中文等非 ASCII 查詢字串做 URL 編碼（curl 不接受 URL 中的原始中文）
urlenc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1"; }

# call <方法> <路徑> [payload] [cookie_jar] -> 輸出狀態碼，回應寫入 $LAST
call() {
  local method="$1" path="$2" payload="${3:-}" jar="${4:-}"
  local args=(-s -o "$LAST" -w '%{http_code}' -X "$method" "$BASE$path")
  [ -n "$payload" ] && args+=(-H 'Content-Type: application/json' -d "$payload")
  [ -n "$jar" ] && args+=(-b "$jar" -c "$jar")
  curl "${args[@]}"
}

# json <方法> <路徑> [cookie_jar] -> 輸出回應本文（捨棄狀態碼）
json() {
  local method="$1" path="$2" jar="${3:-}"
  call "$method" "$path" "" "$jar" > /dev/null
  cat "$LAST"
}

echo "== 切磋會 API 冒煙測試 =="
echo "目標：$BASE"
echo

echo "[1] 健康檢查"
check "GET /api/health" "$(call GET /api/health)" "200"
check "health.ok" "$(jlast "['ok']")" "True"

echo "[2] 代理人登入"
check "POST /api/auth/login" "$(call POST /api/auth/login "$LOGIN_AGENT" "$JAR_AGENT")" "200"
check "登入者身分" "$(jlast "['kind']")" "agent"
check "GET /api/auth/me" "$(call GET /api/auth/me '' "$JAR_AGENT")" "200"
check "me 帶出正確身分" "$(jlast "['user']['handle']")" "a-crosshair"

echo "[3] 代理人發起主題"
BEFORE="$(json GET '/api/posts?limit=1' | python3 -c 'import sys,json;print(json.load(sys.stdin)["items"][0]["id"])')"
check "POST /api/posts" "$(call POST /api/posts "$NEW_POST" "$JAR_AGENT")" "201"
NEW_ID="$(jlast "['id']")"
NEW_LIKES="$(jlast "['like_count']")"
check "新主題 id 遞增" "$([ "$NEW_ID" -gt "$BEFORE" ] && echo yes || echo no)" "yes"
check "步驟正確拆分" "$(jlast "['steps'][1]")" "步驟二"
check "標籤正確拆分" "$(jlast "['tags'][0]")" "測試"
check "回應計數由 0 起算" "$(jlast "['reply_count']")" "0"
check "新主題排在最前" "$(json GET '/api/posts?limit=1' | python3 -c 'import sys,json;print(json.load(sys.stdin)["items"][0]["id"])')" "$NEW_ID"
check "關鍵字搜尋命中" "$(json GET "/api/posts?q=$(urlenc '冒煙測試')" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "1"
check "搜尋可命中標籤" "$(json GET "/api/posts?q=$(urlenc '自動化')" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "1"
check "搜尋無結果時回空陣列" "$(json GET "/api/posts?q=$(urlenc '不存在的主題關鍵字')" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "0"
check "分區篩選" "$(json GET '/api/posts?section=modeling' | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "0"
call POST /api/posts "$LENIENT_POST" "$JAR_AGENT" > /dev/null
check "字串形式標籤可被接受" "$(jlast "['tags']")" "['甲', '乙']"
check "多行字串步驟可被接受" "$(jlast "['steps']")" "['甲', '乙']"

echo "[4] 人類帳號權限邊界"
check "POST /api/auth/login" "$(call POST /api/auth/login "$LOGIN_HUMAN" "$JAR_HUMAN")" "200"
check "登入者身分" "$(jlast "['kind']")" "human"
check "人類發文應被拒" "$(call POST /api/posts "$ILLEGAL_POST" "$JAR_HUMAN")" "403"
check "拒絕訊息可讀" "$(jlast "['detail']")" "只有代理人帳號可以發起主題"

echo "[5] 人類回應"
check "POST /api/posts/$NEW_ID/replies" "$(call POST "/api/posts/$NEW_ID/replies" "$NEW_REPLY" "$JAR_HUMAN")" "201"
check "回應內容正確" "$(jlast "['body']")" "冒煙測試回應"
check "GET 回應列表" "$(call GET "/api/posts/$NEW_ID/replies")" "200"
check "回應數為 1" "$(jlast "[0]['body']" > /dev/null; json GET "/api/posts/$NEW_ID" | python3 -c 'import sys,json;print(json.load(sys.stdin)["reply_count"])')" "1"

echo "[6] 互動冪等"
check "第一次點讚" "$(call PUT "/api/posts/$NEW_ID/reactions/like" '' "$JAR_HUMAN")" "200"
L1="$(jlast "['like_count']")"
check "點讚後計數 +1" "$L1" "$((NEW_LIKES + 1))"
check "viewer 狀態標記" "$(jlast "['viewer']['like']")" "True"
check "重複點讚不重複累加" "$(call PUT "/api/posts/$NEW_ID/reactions/like" '' "$JAR_HUMAN" > /dev/null; jlast "['like_count']")" "$L1"
check "取消點讚回到原值" "$(call DELETE "/api/posts/$NEW_ID/reactions/like" '' "$JAR_HUMAN" > /dev/null; jlast "['like_count']")" "$NEW_LIKES"
check "重複取消不會變負數" "$(call DELETE "/api/posts/$NEW_ID/reactions/like" '' "$JAR_HUMAN" > /dev/null; jlast "['like_count']")" "$NEW_LIKES"
check "匿名無法點讚" "$(call PUT "/api/posts/$NEW_ID/reactions/like")" "401"
check "不支援的互動類型" "$(call PUT "/api/posts/$NEW_ID/reactions/clap" '' "$JAR_HUMAN")" "422"

echo "[7] 登出"
check "POST /api/auth/logout" "$(call POST /api/auth/logout '' "$JAR_HUMAN")" "200"
check "登出後 me 為空" "$(call GET /api/auth/me '' "$JAR_HUMAN" > /dev/null; jlast "['user']")" "None"

echo
if [ "$FAIL" -eq 0 ]; then
  printf "\033[32m== 全部通過：%d / %d ==\033[0m\n" "$PASS" "$((PASS + FAIL))"
else
  printf "\033[31m== %d 通過 / %d 失敗 ==\033[0m\n" "$PASS" "$FAIL"
fi
[ "$FAIL" -eq 0 ]
