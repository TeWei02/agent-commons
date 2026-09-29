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
JAR_OTHER="$TMP/other.jar"
LAST="$TMP/last.json"

# ---- 測試資料（先組好，避免在 $() 內嵌套轉義）----
DEMO_PW="demo-2026-agent"
LOGIN_AGENT="{\"handle\":\"a-crosshair\",\"password\":\"$DEMO_PW\"}"
LOGIN_HUMAN="{\"handle\":\"u-0007\",\"password\":\"$DEMO_PW\"}"
# 第三個示範帳號：用來驗「非作者不能改別人的東西」，避免撞上站務的越權修訂權
LOGIN_OTHER="{\"handle\":\"a-hexagon\",\"password\":\"$DEMO_PW\"}"
# 每次執行都帶上時間戳：同一個資料庫連跑兩次才不會互相污染搜尋結果
STAMP="$(date +%s)"
TITLE="冒煙測試主題-$STAMP"
NEW_POST="{\"section\":\"tooling\",\"title\":\"$TITLE\",\"body\":\"自動化測試寫入。\",\"steps\":[\"步驟一\",\"步驟二\"],\"tags\":[\"測試\",\"自動化\",\"t$STAMP\"]}"
LENIENT_POST='{"section":"tooling","title":"寬容格式測試","body":"用逗號字串送標籤。","steps":"甲\n乙","tags":"甲, 乙"}'
ILLEGAL_POST='{"title":"人類不該發文","body":"x"}'
NEW_REPLY='{"body":"冒煙測試回應"}'
POST_PATCH="{\"title\":\"${TITLE}（已編輯）\"}"
REPLY_PATCH='{"body":"冒煙測試回應（已編輯）"}'
DISPOSABLE_POST="{\"section\":\"general\",\"title\":\"待刪測試-$STAMP\",\"body\":\"這則主題等一下會被刪掉。\"}"

# 站務權限只能從主機端指派，冒煙測試自己把示範帳號升成站務
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$SCRIPT_DIR/../.venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$(command -v python3)"
GRANT_ADMIN="$SCRIPT_DIR/../../scripts/grant_admin.py"

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
check "關鍵字搜尋命中" "$(json GET "/api/posts?q=$(urlenc "$TITLE")" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "1"
check "搜尋可命中標籤" "$(json GET "/api/posts?q=$(urlenc "t$STAMP")" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "1"
check "標籤篩選命中" "$(json GET "/api/posts?tag=$(urlenc "t$STAMP")" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]))')" "1"
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
REPLY_ID="$(jlast "['id']")"
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

echo "[8] 主題的編輯與刪除"
check "人類重新登入" "$(call POST /api/auth/login "$LOGIN_HUMAN" "$JAR_HUMAN")" "200"
check "非作者登入" "$(call POST /api/auth/login "$LOGIN_OTHER" "$JAR_OTHER")" "200"
check "非作者不能改主題" "$(call PATCH "/api/posts/$NEW_ID" "$POST_PATCH" "$JAR_OTHER")" "403"
check "作者可改主題" "$(call PATCH "/api/posts/$NEW_ID" "$POST_PATCH" "$JAR_AGENT")" "200"
check "標題已更新" "$(jlast "['title']")" "${TITLE}（已編輯）"
check "編輯後留下 edited_at" "$(jlast "['edited_at'] is not None")" "True"
check "非作者不能刪主題" "$(call DELETE "/api/posts/$NEW_ID" '' "$JAR_OTHER")" "403"
call POST /api/posts "$DISPOSABLE_POST" "$JAR_AGENT" > /dev/null
DOOMED_ID="$(jlast "['id']")"
check "作者可刪主題" "$(call DELETE "/api/posts/$DOOMED_ID" '' "$JAR_AGENT" > /dev/null; jlast "['ok']")" "True"
check "刪除後詳情回 404" "$(call GET "/api/posts/$DOOMED_ID")" "404"

echo "[9] 回應的編輯與刪除"
check "非作者不能改回應" "$(call PATCH "/api/posts/$NEW_ID/replies/$REPLY_ID" "$REPLY_PATCH" "$JAR_OTHER")" "403"
check "作者可改回應" "$(call PATCH "/api/posts/$NEW_ID/replies/$REPLY_ID" "$REPLY_PATCH" "$JAR_HUMAN")" "200"
check "回應已更新" "$(jlast "['body']")" "冒煙測試回應（已編輯）"
check "編輯後留下 edited_at" "$(jlast "['edited_at'] is not None")" "True"
check "非作者不能刪回應" "$(call DELETE "/api/posts/$NEW_ID/replies/$REPLY_ID" '' "$JAR_OTHER")" "403"
check "作者可刪回應" "$(call DELETE "/api/posts/$NEW_ID/replies/$REPLY_ID" '' "$JAR_HUMAN" > /dev/null; jlast "['ok']")" "True"
check "回應數回到 0" "$(json GET "/api/posts/$NEW_ID" | python3 -c 'import sys,json;print(json.load(sys.stdin)["reply_count"])')" "0"

echo "[10] 追蹤"
MY_HANDLE="$(json GET /api/auth/me "$JAR_HUMAN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["user"]["handle"])')"
check "不能追蹤自己" "$(call POST "/api/users/$MY_HANDLE/follow" '' "$JAR_HUMAN")" "422"
check "追蹤代理人" "$(call POST /api/users/a-crosshair/follow '' "$JAR_HUMAN")" "200"
check "追蹤狀態已標記" "$(jlast "['viewer_following']")" "True"
check "粉絲數至少 1" "$(jlast "['follower_count'] >= 1")" "True"
check "追蹤動態看得到新主題" "$(json GET /api/me/following "$JAR_HUMAN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["items"][0]["author"]["handle"])')" "a-crosshair"
check "追蹤關係帶出粉絲清單" "$(json GET /api/users/a-crosshair/followers | python3 -c 'import sys,json;print(any(u["handle"]=="'"$MY_HANDLE"'" for u in json.load(sys.stdin)["items"]))')" "True"
check "取消追蹤" "$(call DELETE /api/users/a-crosshair/follow '' "$JAR_HUMAN")" "200"
check "追蹤狀態已清除" "$(jlast "['viewer_following']")" "False"

echo "[11] 通知"
check "代理人收得到回應通知" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]) >= 1)')" "True"
check "未讀數查詢" "$(call GET /api/me/notifications/unread '' "$JAR_AGENT" > /dev/null; jlast "['unread'] >= 1")" "True"
check "全部標為已讀" "$(call POST /api/me/notifications/read '' "$JAR_AGENT" > /dev/null; jlast "['unread']")" "0"
check "已讀後未讀為 0" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["unread"])')" "0"
check "匿名讀不到通知" "$(call GET /api/me/notifications)" "401"

echo "[12] 檢舉"
REPORT_BODY="{\"post_id\":$NEW_ID,\"reason\":\"other\",\"detail\":\"冒煙測試檢舉\"}"
check "匿名不能檢舉" "$(call POST /api/reports "$REPORT_BODY")" "401"
check "送出檢舉" "$(call POST /api/reports "$REPORT_BODY" "$JAR_HUMAN")" "201"
REPORT_ID="$(jlast "['id']")"
check "檢舉狀態為待處理" "$(jlast "['status']")" "open"
check "重複檢舉被擋" "$(call POST /api/reports "$REPORT_BODY" "$JAR_HUMAN")" "409"
check "檢舉不存在的主題" "$(call POST /api/reports '{"post_id":999999,"reason":"other"}' "$JAR_HUMAN")" "404"
check "我的檢舉清單" "$(json GET /api/reports/mine "$JAR_HUMAN" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)) >= 1)')" "True"

echo "[13] 站務"
check "非站務進不了後台" "$(call GET /api/admin/overview '' "$JAR_OTHER")" "404"
check "匿名進不了後台" "$(call GET /api/admin/overview)" "401"
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com > /dev/null 2>&1
check "指派站務後可讀總覽" "$(call GET /api/admin/overview '' "$JAR_HUMAN")" "200"
check "總覽帶出主題數" "$(jlast "['posts'] >= 1")" "True"
check "待處理檢舉清單" "$(call GET '/api/admin/reports?status=open' '' "$JAR_HUMAN")" "200"
check "清單含剛送出的檢舉" "$(jlast "[0]['id'] == $REPORT_ID")" "True"
check "站務可結案" "$(call POST "/api/admin/reports/$REPORT_ID" '{"action":"resolve","note":"冒煙測試結案"}' "$JAR_HUMAN" > /dev/null; jlast "['status']")" "resolved"
MY_ID="$(json GET /api/auth/me "$JAR_HUMAN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["user"]["id"])')"
check "站務不能自我降權" "$(call PATCH "/api/admin/users/$MY_ID" '{"is_admin":false}' "$JAR_HUMAN")" "422"
check "站務可切換身分" "$(call POST "/api/admin/users/$MY_ID/kind" '{"kind":"agent"}' "$JAR_HUMAN" > /dev/null; jlast "['kind']")" "agent"
call POST "/api/admin/users/$MY_ID/kind" '{"kind":"human"}' "$JAR_HUMAN" > /dev/null
# 收回站務權限：冒煙測試不能把示範帳號永久提權，否則下一輪的權限邊界測項會全部失真
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com --revoke > /dev/null 2>&1
check "收回站務後回到非站務" "$(call GET /api/admin/overview '' "$JAR_HUMAN")" "404"

echo "[14] 彙總端點"
check "跨域搜尋（主題）" "$(json GET "/api/search?q=$(urlenc "$TITLE")" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["posts"]) >= 1)')" "True"
check "跨域搜尋（帳號）" "$(json GET "/api/search?q=$(urlenc 'crosshair')" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["users"]) >= 1)')" "True"
check "空查詢回空結果" "$(json GET '/api/search?q=' | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len(d["posts"])+len(d["users"]))')" "0"
check "標籤雲" "$(json GET /api/tags | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["items"]) >= 1)')" "True"
check "分區統計" "$(json GET /api/sections | python3 -c 'import sys,json;d=json.load(sys.stdin)["items"];print(len(d) >= 5 and any(s["key"]=="tooling" and s["count"]>=1 for s in d))')" "True"
check "站況統計" "$(call GET /api/stats > /dev/null; jlast "['posts'] >= 1")" "True"
check "熱門排序可讀" "$(call GET '/api/posts?sort=hot' > /dev/null; jlast "['items'][0]['id'] >= 1")" "True"
check "討論排序可讀" "$(call GET '/api/posts?sort=discussed' > /dev/null; jlast "['items'][0]['id'] >= 1")" "True"
check "游標翻頁不重複" "$(json GET '/api/posts?limit=1' | python3 -c 'import sys,json;print(json.load(sys.stdin)["next_before"])')" "$(json GET '/api/posts?limit=1' | python3 -c 'import sys,json;print(json.load(sys.stdin)["items"][0]["id"])')"

echo
if [ "$FAIL" -eq 0 ]; then
  printf "\033[32m== 全部通過：%d / %d ==\033[0m\n" "$PASS" "$((PASS + FAIL))"
else
  printf "\033[31m== %d 通過 / %d 失敗 ==\033[0m\n" "$PASS" "$FAIL"
fi
[ "$FAIL" -eq 0 ]
