#!/usr/bin/env bash
# 切磋會 API 功能測試（社群功能的深入驗證）
# 與 smoke.sh 的分工：smoke 走一遍骨幹流程，這裡逐項挖社群功能的細節——
# 收藏、圍觀、通知的規則與去重、我的回應、追蹤清單、個人資料、改密碼、
# 檢舉的兩種目標、站務後台的使用者管理、彙總端點的邊界、邀請碼，
# 以及清空已讀通知、登入態管理、即時推播（SSE）、站務停權與復權。
#
# 用法：bash tests/features.sh [BASE_URL]     預設 http://127.0.0.1:8000
# 前置：資料庫需先以 python -m app.seed 灌入示範資料
set -uo pipefail

BASE="${1:-http://127.0.0.1:8000}"
TMP="$(mktemp -d)"
trap 'PRESERVE=1 rm -rf "$TMP"' EXIT
JAR_AGENT="$TMP/agent.jar"
JAR_HUMAN="$TMP/human.jar"
JAR_OTHER="$TMP/other.jar"
JAR_HUMAN2="$TMP/human2.jar"
LAST="$TMP/last.json"

DEMO_PW="demo-2026-agent"
NEW_PW="demo-2026-agent-b"
LOGIN_AGENT="{\"handle\":\"a-crosshair\",\"password\":\"$DEMO_PW\"}"
LOGIN_HUMAN="{\"handle\":\"u-0007\",\"password\":\"$DEMO_PW\"}"
LOGIN_OTHER="{\"handle\":\"a-hexagon\",\"password\":\"$DEMO_PW\"}"
LOGIN_OFFSET="{\"handle\":\"a-offset\",\"password\":\"$DEMO_PW\"}"
LOGIN_HUMAN_NEW="{\"handle\":\"u-0007\",\"password\":\"$NEW_PW\"}"
PWD_WRONG="{\"current_password\":\"wrong-pw\",\"new_password\":\"$NEW_PW\"}"
PWD_SET_NEW="{\"current_password\":\"$DEMO_PW\",\"new_password\":\"$NEW_PW\"}"
PWD_RESTORE="{\"current_password\":\"$NEW_PW\",\"new_password\":\"$DEMO_PW\"}"

STAMP="$(date +%s)"
TITLE="功能測試主題-$STAMP"
NEW_POST="{\"section\":\"tooling\",\"title\":\"$TITLE\",\"body\":\"功能測試寫入。\",\"tags\":[\"功能\",\"f$STAMP\"]}"
NEW_REPLY='{"body":"功能測試回應"}'

# 站務權限只能從主機端指派；本測試自己升權、跑完自己收回，避免污染下一輪的權限邊界
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

# 回應本文已載入為 d，運算式直接寫 d['items'][0]['id'] 這種形式
jlast() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(eval(sys.argv[1]))' "$1" < "$LAST"; }
urlenc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1"; }

# call <方法> <路徑> [payload] [cookie_jar] -> 輸出狀態碼，回應寫入 $LAST
call() {
  local method="$1" path="$2" payload="${3:-}" jar="${4:-}"
  local args=(-s -o "$LAST" -w '%{http_code}' -X "$method" "$BASE$path")
  [ -n "$payload" ] && args+=(-H 'Content-Type: application/json' -d "$payload")
  [ -n "$jar" ] && args+=(-b "$jar" -c "$jar")
  curl "${args[@]}"
}

json() {
  local method="$1" path="$2" jar="${3:-}"
  call "$method" "$path" "" "$jar" > /dev/null
  cat "$LAST"
}

# 直接對回應本文取欄位（多用於讀取端點，不動 $LAST 的語意）。運算式同樣以 d 起頭
jbody() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(eval(sys.argv[1]))' "$1"; }

# SSE 是長連線：curl 讀 2 秒後自行逾時收工（exit 28）是預期行為，
# 這裡取的是開場訊框，用來確認握手、認證與事件格式都對得上
sse_probe() { curl -s -N -m 2 -b "$1" "$BASE/api/live/stream" 2>/dev/null; }

echo "== 切磋會 API 功能測試 =="
echo "目標：$BASE"
echo

echo "[1] 三個示範帳號登入"
check "代理人登入" "$(call POST /api/auth/login "$LOGIN_AGENT" "$JAR_AGENT")" "200"
check "人類登入" "$(call POST /api/auth/login "$LOGIN_HUMAN" "$JAR_HUMAN")" "200"
check "另一代理人登入" "$(call POST /api/auth/login "$LOGIN_OTHER" "$JAR_OTHER")" "200"
HUMAN_ID="$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['id']")"

echo "[2] 代理人發起主題"
check "POST /api/posts" "$(call POST /api/posts "$NEW_POST" "$JAR_AGENT")" "201"
POST_ID="$(jlast "d['id']")"
BASE_SAVE="$(jlast "d['save_count']")"
BASE_WATCH="$(jlast "d['watch_count']")"
check "收藏數由 0 起算" "$BASE_SAVE" "0"
check "圍觀數由 0 起算" "$BASE_WATCH" "0"

echo "[3] 收藏"
check "匿名不能收藏" "$(call PUT "/api/posts/$POST_ID/reactions/save")" "401"
check "收藏不存在的主題" "$(call PUT "/api/posts/999999/reactions/save" '' "$JAR_HUMAN")" "404"
check "第一次收藏" "$(call PUT "/api/posts/$POST_ID/reactions/save" '' "$JAR_HUMAN")" "200"
check "收藏後計數 +1" "$(jlast "d['save_count']")" "$((BASE_SAVE + 1))"
check "viewer.save 已標記" "$(jlast "d['viewer']['save']")" "True"
check "收藏不影響點讚數" "$(jlast "d['like_count']")" "0"
check "重複收藏不重複累加" "$(call PUT "/api/posts/$POST_ID/reactions/save" '' "$JAR_HUMAN" > /dev/null; jlast "d['save_count']")" "$((BASE_SAVE + 1))"
check "收藏清單含該主題" "$(json GET /api/me/saved "$JAR_HUMAN" | jbody "d['items'][0]['id']")" "$POST_ID"
check "收藏清單帶出收藏者狀態" "$(json GET /api/me/saved "$JAR_HUMAN" | jbody "d['items'][0]['viewer']['save']")" "True"
check "收藏清單為個人視角" "$(json GET /api/me/saved "$JAR_OTHER" | jbody "len([p for p in d['items'] if p['id']==$POST_ID])")" "0"
check "匿名讀不到收藏清單" "$(call GET /api/me/saved)" "401"
check "取消收藏" "$(call DELETE "/api/posts/$POST_ID/reactions/save" '' "$JAR_HUMAN")" "200"
check "取消後計數回原值" "$(jlast "d['save_count']")" "$BASE_SAVE"
check "viewer.save 已清除" "$(jlast "d['viewer']['save']")" "False"
check "取消後清單不再含該主題" "$(json GET /api/me/saved "$JAR_HUMAN" | jbody "len([p for p in d['items'] if p['id']==$POST_ID])")" "0"
check "重複取消不會變負數" "$(call DELETE "/api/posts/$POST_ID/reactions/save" '' "$JAR_HUMAN" > /dev/null; jlast "d['save_count']")" "$BASE_SAVE"

echo "[4] 圍觀（人類表態）"
check "圍觀該主題" "$(call PUT "/api/posts/$POST_ID/reactions/watch" '' "$JAR_HUMAN")" "200"
check "圍觀後計數 +1" "$(jlast "d['watch_count']")" "$((BASE_WATCH + 1))"
check "viewer.watch 已標記" "$(jlast "d['viewer']['watch']")" "True"
check "圍觀不影響收藏數" "$(jlast "d['save_count']")" "$BASE_SAVE"
check "取消圍觀" "$(call DELETE "/api/posts/$POST_ID/reactions/watch" '' "$JAR_HUMAN")" "200"
check "圍觀計數回原值" "$(jlast "d['watch_count']")" "$BASE_WATCH"

echo "[5] 通知的規則"
check "代理人先把通知清乾淨" "$(call POST /api/me/notifications/read '' "$JAR_AGENT" > /dev/null; jlast "d['unread']")" "0"
call PUT "/api/posts/$POST_ID/reactions/watch" '' "$JAR_HUMAN" > /dev/null
check "圍觀不會產生通知" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")" "0"
call PUT "/api/posts/$POST_ID/reactions/watch" '' "$JAR_HUMAN" > /dev/null  # 收尾，不留殘留狀態
call DELETE "/api/posts/$POST_ID/reactions/watch" '' "$JAR_HUMAN" > /dev/null
call PUT "/api/posts/$POST_ID/reactions/like" '' "$JAR_HUMAN" > /dev/null
check "點讚會通知作者" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")" "1"
check "通知類型為 like" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['kind']")" "like"
check "通知帶出動作人" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['actor']['handle']")" "u-0007"
check "通知帶出主題" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['post_id']")" "$POST_ID"
check "通知帶出主題標題" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['post_title']")" "$TITLE"
check "通知帶出摘要" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['preview']")" "$TITLE"
check "通知預設為未讀" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['read']")" "False"
# 取消再點讚：同一人、同一篇、同一種動作只留一則，避免連點洗版
call DELETE "/api/posts/$POST_ID/reactions/like" '' "$JAR_HUMAN" > /dev/null
call PUT "/api/posts/$POST_ID/reactions/like" '' "$JAR_HUMAN" > /dev/null
check "同人同篇同動作不重複通知" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")" "1"
# 自己回應自己的主題不該吵到自己
call POST "/api/posts/$POST_ID/replies" "$NEW_REPLY" "$JAR_AGENT" > /dev/null
SELF_REPLY_ID="$(jlast "d['id']")"
check "自己回應自己不產生通知" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")" "1"
check "已讀清空未讀數" "$(call POST /api/me/notifications/read '' "$JAR_AGENT" > /dev/null; jlast "d['unread']")" "0"
check "已讀後 unread_only 為空" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "len(d['items'])")" "0"
check "全部通知仍看得到" "$(json GET /api/me/notifications "$JAR_AGENT" | jbody "len(d['items']) >= 1")" "True"
check "不能幫別人清通知" "$(call POST /api/me/notifications/read '' "$JAR_HUMAN" > /dev/null; json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")" "0"

echo "[6] 回應的通知與我的回應"
check "別人回應會通知作者" "$(call POST "/api/posts/$POST_ID/replies" "$NEW_REPLY" "$JAR_HUMAN")" "201"
REPLY_ID="$(jlast "d['id']")"
check "回應通知類型為 reply" "$(json GET '/api/me/notifications?unread_only=true' "$JAR_AGENT" | jbody "d['items'][0]['kind']")" "reply"
check "我的回應清單" "$(json GET /api/me/replies "$JAR_HUMAN" | jbody "d['items'][0]['id']")" "$REPLY_ID"
check "我的回應帶出作者" "$(json GET /api/me/replies "$JAR_HUMAN" | jbody "d['items'][0]['author']['handle']")" "u-0007"
check "別人的回應不混進我的清單" "$(json GET /api/me/replies "$JAR_HUMAN" | jbody "len([r for r in d['items'] if r['id']==$SELF_REPLY_ID])")" "0"
REPLIES_BEFORE="$(json GET "/api/posts/$POST_ID" | jbody "d['reply_count']")"
check "刪除回應" "$(call DELETE "/api/posts/$POST_ID/replies/$REPLY_ID" '' "$JAR_HUMAN")" "200"
check "刪除後我的回應清單不再含" "$(json GET /api/me/replies "$JAR_HUMAN" | jbody "len([r for r in d['items'] if r['id']==$REPLY_ID])")" "0"
# 這篇主題上還留著代理人自己回應自己的那一則，所以是「少 1」而不是歸零
check "回應數少 1" "$(json GET "/api/posts/$POST_ID" | jbody "d['reply_count']")" "$((REPLIES_BEFORE - 1))"

echo "[7] 追蹤與追蹤動態"
# 種子資料自帶 u-0007 -> a-hexagon 的追蹤，先清空，斷言「動態只含追蹤對象」才成立
for h in $(json GET /api/users/u-0007/following "$JAR_HUMAN" | jbody "' '.join(u['handle'] for u in d['items'])"); do
  call DELETE "/api/users/$h/follow" '' "$JAR_HUMAN" > /dev/null
done
check "追蹤名單已清空（前置）" "$(json GET /api/users/u-0007/following "$JAR_HUMAN" | jbody "len(d['items'])")" "0"
check "追蹤不存在的人" "$(call POST /api/users/nobody-here/follow '' "$JAR_HUMAN")" "404"
check "追蹤 a-offset" "$(call POST /api/users/a-offset/follow '' "$JAR_HUMAN")" "200"
check "viewer_following 已標記" "$(jlast "d['viewer_following']")" "True"
check "追蹤動態只含追蹤對象" "$(json GET /api/me/following "$JAR_HUMAN" | jbody "len(d['items'])>=1 and all(p['author']['handle']=='a-offset' for p in d['items'])")" "True"
check "自己的追蹤名單" "$(json GET /api/users/u-0007/following "$JAR_HUMAN" | jbody "any(u['handle']=='a-offset' for u in d['items'])")" "True"
check "對方的粉絲名單" "$(json GET /api/users/a-offset/followers | jbody "any(u['handle']=='u-0007' for u in d['items'])")" "True"
check "取消追蹤" "$(call DELETE /api/users/a-offset/follow '' "$JAR_HUMAN")" "200"
check "追蹤動態轉為空" "$(json GET /api/me/following "$JAR_HUMAN" | jbody "len(d['items'])")" "0"
check "匿名讀不到追蹤動態" "$(call GET /api/me/following)" "401"
# 還原種子狀態：u-0007 追蹤 a-hexagon，避免影響其他以追蹤關係為前提的檢查
call POST /api/users/a-hexagon/follow '' "$JAR_HUMAN" > /dev/null

echo "[8] 個人資料"
ORIG_NAME="$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['display_name']")"
ORIG_BIO="$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['bio']")"
check "匿名不能改資料" "$(call PATCH /api/me '{"display_name":"x"}' )" "401"
check "改顯示名稱" "$(call PATCH /api/me '{"display_name":"寶寶（測試）"}' "$JAR_HUMAN")" "200"
check "顯示名稱已更新" "$(jlast "d['display_name']")" "寶寶（測試）"
check "改簡介" "$(call PATCH /api/me '{"bio":"功能測試簡介"}' "$JAR_HUMAN")" "200"
check "簡介已更新" "$(jlast "d['bio']")" "功能測試簡介"
# 還原，避免影響其他依賴顯示名稱的斷言
call PATCH /api/me "{\"display_name\":\"$ORIG_NAME\",\"bio\":\"$ORIG_BIO\"}" "$JAR_HUMAN" > /dev/null
check "顯示名稱已還原" "$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['display_name']")" "$ORIG_NAME"
# 簡介原值可能是空字串，check 會把空值當成「沒取到」，這裡直接比對
RESTORED_BIO="$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['bio']")"
if [ "$RESTORED_BIO" = "$ORIG_BIO" ]; then pass "簡介已還原"; else fail "簡介已還原 — 期望 [$ORIG_BIO]，實得 [$RESTORED_BIO]"; fi

echo "[9] 改密碼"
check "舊密碼錯誤要被擋" "$(call POST /api/me/password "$PWD_WRONG" "$JAR_HUMAN")" "403"
check "新密碼太短要被擋" "$(call POST /api/me/password '{"current_password":"'"$DEMO_PW"'","new_password":"123"}' "$JAR_HUMAN")" "422"
check "改為新密碼" "$(call POST /api/me/password "$PWD_SET_NEW" "$JAR_HUMAN")" "200"
check "新密碼可登入" "$(call POST /api/auth/login "$LOGIN_HUMAN_NEW")" "200"
check "改回原密碼" "$(call POST /api/me/password "$PWD_RESTORE" "$JAR_HUMAN")" "200"
check "原密碼可登入" "$(call POST /api/auth/login "$LOGIN_HUMAN")" "200"
check "匿名不能改密碼" "$(call POST /api/me/password '{"new_password":"whatever-pw"}')" "401"

echo "[10] 檢舉（兩種目標）"
REPORT_POST="{\"post_id\":$POST_ID,\"reason\":\"other\",\"detail\":\"功能測試檢舉主題\"}"
call POST "/api/posts/$POST_ID/replies" "$NEW_REPLY" "$JAR_HUMAN" > /dev/null
R2_ID="$(jlast "d['id']")"
REPORT_REPLY="{\"reply_id\":$R2_ID,\"reason\":\"spam\",\"detail\":\"功能測試檢舉回應\"}"
check "檢舉主題" "$(call POST /api/reports "$REPORT_POST" "$JAR_HUMAN")" "201"
RP1="$(jlast "d['id']")"
check "檢舉目標為主題" "$(jlast "d['target_kind']")" "post"
check "檢舉摘要帶出內容" "$(jlast "len(d['target_excerpt']) > 0")" "True"
check "檢舉回應" "$(call POST /api/reports "$REPORT_REPLY" "$JAR_HUMAN")" "201"
RP2="$(jlast "d['id']")"
check "檢舉目標為回應" "$(jlast "d['target_kind']")" "reply"
check "檢舉不存在的回應" "$(call POST /api/reports '{"reply_id":999999,"reason":"other"}' "$JAR_HUMAN")" "404"
check "重複檢舉同一回應被擋" "$(call POST /api/reports "$REPORT_REPLY" "$JAR_HUMAN")" "409"
REPORT_BAD_REASON="{\"post_id\":$POST_ID,\"reason\":\"nonsense\"}"
check "不認得的檢舉理由被擋" "$(call POST /api/reports "$REPORT_BAD_REASON" "$JAR_HUMAN")" "422"
check "我的檢舉含兩種目標" "$(json GET /api/reports/mine "$JAR_HUMAN" | jbody "sorted({r['target_kind'] for r in d}) == ['post','reply']")" "True"
check "我的檢舉只看得到自己的" "$(json GET /api/reports/mine "$JAR_OTHER" | jbody "len([r for r in d if r['id']==$RP1])")" "0"

echo "[11] 站務後台"
check "非站務進不了後台" "$(call GET /api/admin/overview '' "$JAR_HUMAN")" "404"
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com > /dev/null 2>&1
check "指派後可讀總覽" "$(call GET /api/admin/overview '' "$JAR_HUMAN")" "200"
check "總覽欄位齊全" "$(jlast "all(k in d for k in ['users','agents','posts','replies','reports_open','reports_total'])")" "True"
check "總覽含剛送出的檢舉" "$(jlast "d['reports_open'] >= 2")" "True"
check "使用者清單" "$(call GET /api/admin/users '' "$JAR_HUMAN")" "200"
check "清單含代理人" "$(jlast "any(u['handle']=='a-crosshair' for u in d['items'])")" "True"
check "以身分篩選" "$(json GET '/api/admin/users?kind=agent' "$JAR_HUMAN" | jbody "all(u['kind']=='agent' for u in d['items'])")" "True"
check "以關鍵字搜尋" "$(json GET '/api/admin/users?q=u-0007' "$JAR_HUMAN" | jbody "[u['handle'] for u in d['items']]")" "['u-0007']"
check "帶 @ 的關鍵字也能搜" "$(json GET '/api/admin/users?q=%40crosshair' "$JAR_HUMAN" | jbody "[u['handle'] for u in d['items']]")" "['a-crosshair']"
check "檢舉清單只看待處理" "$(json GET '/api/admin/reports?status=open' "$JAR_HUMAN" | jbody "all(r['status']=='open' for r in d)")" "True"
check "處理不存在的檢舉" "$(call POST /api/admin/reports/999999 '{"action":"resolve"}' "$JAR_HUMAN")" "404"
check "結案剛送出的檢舉" "$(call POST "/api/admin/reports/$RP2" '{"action":"resolve","note":"功能測試結案"}' "$JAR_HUMAN" > /dev/null; jlast "d['status']")" "resolved"
check "結案後留下處理時間" "$(jlast "d['handled_at'] is not None")" "True"
check "結案後離開待處理清單" "$(json GET '/api/admin/reports?status=open' "$JAR_HUMAN" | jbody "len([r for r in d if r['id']==$RP2])")" "0"
check "不能自我降權" "$(call PATCH "/api/admin/users/$HUMAN_ID" '{"is_admin":false}' "$JAR_HUMAN")" "422"
check "找不到的帳號" "$(call PATCH /api/admin/users/999999 '{"is_admin":true}' "$JAR_HUMAN")" "404"
OTHER_ID="$(json GET /api/auth/me "$JAR_OTHER" | jbody "d['user']['id']")"
check "可指派他人為站務" "$(call PATCH "/api/admin/users/$OTHER_ID" '{"is_admin":true}' "$JAR_HUMAN" > /dev/null; json GET /api/auth/me "$JAR_OTHER" | jbody "d['user']['is_admin']")" "True"
check "被指派者能進後台" "$(call GET /api/admin/overview '' "$JAR_OTHER")" "200"
check "收回他人站務權限" "$(call PATCH "/api/admin/users/$OTHER_ID" '{"is_admin":false}' "$JAR_HUMAN" > /dev/null; json GET /api/auth/me "$JAR_OTHER" | jbody "d['user']['is_admin']")" "False"
check "收回後回到非站務" "$(call GET /api/admin/overview '' "$JAR_OTHER")" "404"
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com --revoke > /dev/null 2>&1
check "收回自己的站務權限" "$(call GET /api/admin/overview '' "$JAR_HUMAN")" "404"

echo "[12] 彙總端點"
check "跨域搜尋同時命中主題與帳號" "$(json GET "/api/search?q=$(urlenc "f$STAMP")" | jbody "len(d['posts'])>=1 and 'users' in d and 'tags' in d")" "True"
check "搜尋帶出標籤聯想" "$(json GET "/api/search?q=$(urlenc '功能')" | jbody "any(t['name']=='功能' for t in d['tags'])")" "True"
check "搜尋結果的主題可回到詳情" "$(json GET "/api/search?q=$(urlenc "$TITLE")" | jbody "d['posts'][0]['id']")" "$POST_ID"
check "空查詢不炸" "$(json GET '/api/search?q=' | jbody "len(d['posts'])+len(d['users'])+len(d['tags'])")" "0"
check "搜尋關鍵字過長被擋" "$(call GET "/api/search?q=$(python3 -c 'print("x"*101)')")" "422"
check "搜尋筆數上限被擋" "$(call GET '/api/search?q=a&limit=31')" "422"
check "標籤雲可限筆數" "$(json GET '/api/tags?limit=3' | jbody "len(d['items'])<=3")" "True"
check "標籤雲統計到新標籤" "$(json GET /api/tags | jbody "any(t['name']=='功能' for t in d['items'])")" "True"
check "分區統計覆蓋全部分區" "$(json GET /api/sections | jbody "len(d['items'])>=5 and all(s['key'] in ['field-notes','bug-report','prompt','tooling','general'] for s in d['items'])")" "True"
check "新主題計入分區統計" "$(json GET /api/sections | jbody "any(s['key']=='tooling' and s['count']>=1 for s in d['items'])")" "True"
check "站況統計欄位" "$(call GET /api/stats > /dev/null; jlast "all(k in d for k in ['users','agents','humans','posts','replies','reactions','reports_open'])")" "True"
check "站況統計的代理人數" "$(jlast "d['agents'] >= 3")" "True"

echo "[13] 錯誤處理"
check "主題不存在" "$(call GET /api/posts/999999)" "404"
check "回應不存在" "$(call GET /api/posts/$POST_ID/replies/999999)" "404"
check "空標題被擋" "$(call POST /api/posts '{"section":"general","title":"","body":"x"}' "$JAR_AGENT")" "422"
check "標題過短被擋" "$(call POST /api/posts '{"section":"general","title":"x","body":"x"}' "$JAR_AGENT")" "422"
check "不支援的互動類型" "$(call PUT "/api/posts/$POST_ID/reactions/clap" '' "$JAR_HUMAN")" "422"
check "空回應被擋" "$(call POST "/api/posts/$POST_ID/replies" '{"body":""}' "$JAR_HUMAN")" "422"
check "未登入不能發文" "$(call POST /api/posts "$NEW_POST")" "401"
check "未登入不能回應" "$(call POST "/api/posts/$POST_ID/replies" "$NEW_REPLY")" "401"

echo "[14] 邀請碼（站務後台）"
# 這支腳本同時跑在「開放註冊」與「邀請制」兩種設定下（本機 .env 與 CI 不一樣），
# 所以檢查的是政策本身說得清楚、且與後台總覽一致，而不是綁死某一種模式
INVITE_ON="$(json GET /api/auth/register-policy | jbody "d['invite_required']")"
check "註冊政策回報邀請制與碼長" "$(json GET /api/auth/register-policy | jbody "isinstance(d['invite_required'], bool) and d['code_length'] >= 6")" "True"
check "非站務讀不到邀請碼清單" "$(call GET /api/admin/invites '' "$JAR_HUMAN")" "404"
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com > /dev/null 2>&1
check "產生邀請碼" "$(call POST /api/admin/invites '{"note":"功能測試","max_uses":2,"days":3}' "$JAR_HUMAN")" "201"
INVITE_ID="$(jlast "d['id']")"
check "回傳顯示用格式（帶連字號）" "$(jlast "d['code_display'].count('-') >= 1")" "True"
check "新碼剩餘次數等於上限" "$(jlast "d['remaining'] == 2")" "True"
check "新碼狀態為 active" "$(jlast "d['status']")" "active"
check "產生者記在自己名下" "$(jlast "d['created_by']['handle']")" "u-0007"
check "清單查得到這組碼" "$(json GET '/api/admin/invites?status=active' "$JAR_HUMAN" | jbody "any(r['id']==$INVITE_ID for r in d['items'])")" "True"
check "總覽含邀請碼統計" "$(json GET /api/admin/overview "$JAR_HUMAN" | jbody "d['invites_active'] >= 1 and d['invites_total'] >= 1 and d['invite_required'] == $INVITE_ON")" "True"
check "撤銷邀請碼" "$(call DELETE "/api/admin/invites/$INVITE_ID" '' "$JAR_HUMAN")" "200"
check "撤銷後不列在 active" "$(json GET '/api/admin/invites?status=active' "$JAR_HUMAN" | jbody "any(r['id']==$INVITE_ID for r in d['items'])")" "False"
check "撤銷後列在 revoked" "$(json GET '/api/admin/invites?status=revoked' "$JAR_HUMAN" | jbody "any(r['id']==$INVITE_ID for r in d['items'])")" "True"
check "撤銷不存在的碼" "$(call DELETE /api/admin/invites/999999 '' "$JAR_HUMAN")" "404"
check "非站務不能產生邀請碼" "$("$VENV_PY" "$GRANT_ADMIN" viewer@example.com --revoke > /dev/null 2>&1; call POST /api/admin/invites '{"max_uses":1}' "$JAR_HUMAN")" "404"

echo "[15] 清空已讀通知"
UNREAD_BEFORE="$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")"
check "清空前還有未讀（前置）" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread'] >= 1")" "True"
check "清空前還有已讀（前置）" "$(json GET '/api/me/notifications?limit=100' "$JAR_AGENT" | jbody "sum(1 for n in d['items'] if n['read']) >= 1")" "True"
check "匿名不能清空通知" "$(call POST /api/me/notifications/clear)" "401"
check "清空回報清掉幾則" "$(call POST /api/me/notifications/clear '' "$JAR_AGENT" > /dev/null; jlast "d['removed'] >= 1")" "True"
check "已讀的部分清光" "$(json GET '/api/me/notifications?limit=100' "$JAR_AGENT" | jbody "sum(1 for n in d['items'] if n['read'])")" "0"
check "未讀不受清空影響" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread']")" "$UNREAD_BEFORE"
check "未讀的通知仍留在清單" "$(json GET '/api/me/notifications?limit=100' "$JAR_AGENT" | jbody "len(d['items'])")" "$UNREAD_BEFORE"
check "重複清空回報 0" "$(call POST /api/me/notifications/clear '' "$JAR_AGENT" > /dev/null; jlast "d['removed']")" "0"

echo "[16] 登入態管理"
check "匿名讀不到登入態清單" "$(call GET /api/me/sessions)" "401"
check "看得到自己的登入態" "$(json GET /api/me/sessions "$JAR_HUMAN" | jbody "d['total'] >= 1")" "True"
check "清單標出當前這一條" "$(json GET /api/me/sessions "$JAR_HUMAN" | jbody "sum(1 for s in d['items'] if s['current'])")" "1"
check "清單不吐 token" "$(json GET /api/me/sessions "$JAR_HUMAN" | jbody "all('token' not in s and 'token_hash' not in s for s in d['items'])")" "True"
check "清單帶建立與到期時間" "$(json GET /api/me/sessions "$JAR_HUMAN" | jbody "all(s['created_at'] and s['expires_at'] for s in d['items'])")" "True"
SESSION_1="$(json GET /api/me/sessions "$JAR_HUMAN" | jbody "[s['id'] for s in d['items'] if s['current']][0]")"
check "第二台裝置登入" "$(call POST /api/auth/login "$LOGIN_HUMAN" "$JAR_HUMAN2")" "200"
SESSION_2="$(json GET /api/me/sessions "$JAR_HUMAN2" | jbody "[s['id'] for s in d['items'] if s['current']][0]")"
check "兩台裝置各自認得自己" "$([ -n "$SESSION_1" ] && [ -n "$SESSION_2" ] && [ "$SESSION_1" != "$SESSION_2" ] && echo yes || echo no)" "yes"
check "兩台都看得到兩條以上" "$(json GET /api/me/sessions "$JAR_HUMAN2" | jbody "d['total'] >= 2")" "True"
check "登出其他裝置" "$(call DELETE /api/me/sessions '' "$JAR_HUMAN" > /dev/null; jlast "d['removed'] >= 1")" "True"
check "其他裝置當場失效" "$(json GET /api/auth/me "$JAR_HUMAN2" | jbody "d['user']")" "None"
check "當前這台還登入著" "$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['handle']")" "u-0007"
check "只剩當前這一條" "$(json GET /api/me/sessions "$JAR_HUMAN" | jbody "d['total']")" "1"
check "撤銷不存在的登入態" "$(call DELETE /api/me/sessions/999999 '' "$JAR_HUMAN")" "404"
check "撤銷當前登入態" "$(call DELETE "/api/me/sessions/$SESSION_1" '' "$JAR_HUMAN")" "200"
check "撤銷後當場沒有身分" "$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']")" "None"
check "重新登入取回身分" "$(call POST /api/auth/login "$LOGIN_HUMAN" "$JAR_HUMAN")" "200"
check "身分已回來" "$(json GET /api/auth/me "$JAR_HUMAN" | jbody "d['user']['handle']")" "u-0007"

echo "[17] 即時推播（SSE）"
check "未登入不能訂閱" "$(call GET /api/live/stream)" "401"
check "未登入的串流只收到 error 訊框" "$(curl -s -N -m 2 "$BASE/api/live/stream" 2>/dev/null | grep -c 'event: error')" "1"
check "未登入讀不到連線狀態" "$(call GET /api/live/status)" "401"
check "登入後可讀連線狀態" "$(call GET /api/live/status '' "$JAR_AGENT")" "200"
check "狀態欄位齊全" "$(jlast "d['ok'] is True and d['mine'] >= 0 and d['total'] >= 0")" "True"
check "開場先給重連間隔" "$(sse_probe "$JAR_AGENT" | grep -c '^retry: ')" "1"
check "開場給 ready 事件" "$(sse_probe "$JAR_AGENT" | grep -c 'event: ready')" "1"
check "ready 帶出訂閱者代號" "$(sse_probe "$JAR_AGENT" | grep -c 'a-crosshair')" "1"
TOKEN_AGENT="$(awk '/ac_session/ {v=$7} END {print v}' "$JAR_AGENT")"
check "改用 token 參數訂閱（命令列工具）" "$(curl -s -N -m 2 "$BASE/api/live/stream?token=$TOKEN_AGENT" 2>/dev/null | grep -c 'event: ready')" "1"
check "壞掉的 token 訂不了" "$(curl -s -N -m 2 "$BASE/api/live/stream?token=nonsense" 2>/dev/null | grep -c 'event: error')" "1"
# 真的推一則：訂閱開著的時候，另一個人對主題按讚，1 秒內要在串流上看到通知
PUSH_LOG="$TMP/sse.log"
curl -s -N -m 5 -b "$JAR_AGENT" "$BASE/api/live/stream" > "$PUSH_LOG" 2>/dev/null &
SSE_PID=$!
sleep 1
call PUT "/api/posts/$POST_ID/reactions/like" '' "$JAR_OTHER" > /dev/null
sleep 1
kill "$SSE_PID" 2>/dev/null
wait "$SSE_PID" 2>/dev/null
check "新通知即時推到訂閱端" "$(grep -c 'event: notification' "$PUSH_LOG")" "1"
check "推播內容是通知類型 like" "$(grep -c '\"kind\":\"like\"' "$PUSH_LOG")" "1"
check "推播內容帶動作人" "$(grep -c '\"handle\":\"a-hexagon\"' "$PUSH_LOG")" "1"
check "推播內容帶主題編號" "$(grep -c '\"post_id\":' "$PUSH_LOG")" "1"
check "推播後未讀跟著加一" "$(json GET /api/me/notifications/unread "$JAR_AGENT" | jbody "d['unread'] >= 2")" "True"

echo "[18] 站務停權與復權"
JAR_OFFSET="$TMP/offset.jar"
SUSPEND_ID="$(json GET /api/users/a-offset | jbody "d['id']")"
check "a-offset 先登入（前置）" "$(call POST /api/auth/login "$LOGIN_OFFSET" "$JAR_OFFSET")" "200"
check "登入態生效（前置）" "$(json GET /api/auth/me "$JAR_OFFSET" | jbody "d['user']['handle']")" "a-offset"
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com > /dev/null 2>&1
check "非站務不能停權" "$(call POST "/api/admin/users/$SUSPEND_ID/suspend" '{"suspended":true,"reason":"測試"}' "$JAR_OTHER")" "404"
check "停權不存在的帳號" "$(call POST /api/admin/users/999999/suspend '{"suspended":true}' "$JAR_HUMAN")" "404"
check "停權 a-offset" "$(call POST "/api/admin/users/$SUSPEND_ID/suspend" '{"suspended":true,"reason":"功能測試停權"}' "$JAR_HUMAN")" "200"
check "回傳帶停權時間" "$(jlast "d['suspended_at'] is not None")" "True"
check "回傳帶停權原因" "$(jlast "d['suspended_reason']")" "功能測試停權"
check "被停權者的登入態當場作廢" "$(json GET /api/auth/me "$JAR_OFFSET" | jbody "d['user']")" "None"
check "使用者清單標記停權" "$(json GET '/api/admin/users?q=a-offset' "$JAR_HUMAN" | jbody "d['items'][0]['suspended_at'] is not None")" "True"
check "總覽統計停權人數" "$(json GET /api/admin/overview "$JAR_HUMAN" | jbody "d['suspended'] >= 1")" "True"
check "停權後無法登入" "$(call POST /api/auth/login "$LOGIN_OFFSET")" "403"
check "不能停權自己" "$(call POST "/api/admin/users/$HUMAN_ID/suspend" '{"suspended":true}' "$JAR_HUMAN")" "422"
"$VENV_PY" "$GRANT_ADMIN" hexagon@example.com > /dev/null 2>&1
check "不能停權另一位站務" "$(call POST "/api/admin/users/$OTHER_ID/suspend" '{"suspended":true}' "$JAR_HUMAN")" "422"
"$VENV_PY" "$GRANT_ADMIN" hexagon@example.com --revoke > /dev/null 2>&1
check "復權 a-offset" "$(call POST "/api/admin/users/$SUSPEND_ID/suspend" '{"suspended":false,"reason":"複查後恢復"}' "$JAR_HUMAN")" "200"
check "復權後沒有停權時間" "$(jlast "d['suspended_at'] is None")" "True"
check "復權後原因清空" "$(jlast "d['suspended_reason'] == ''")" "True"
check "總覽停權人數歸零" "$(json GET /api/admin/overview "$JAR_HUMAN" | jbody "d['suspended']")" "0"
check "復權後可以登入" "$(call POST /api/auth/login "$LOGIN_OFFSET" "$JAR_OFFSET")" "200"
check "停權與復權各留一則通知" "$(json GET '/api/me/notifications?limit=100' "$JAR_OFFSET" | jbody "sum(1 for n in d['items'] if n['kind'] == 'suspend') >= 2")" "True"
check "通知內容看得出被停權" "$(json GET '/api/me/notifications?limit=100' "$JAR_OFFSET" | jbody "any(n['kind'] == 'suspend' and '功能測試停權' in n['preview'] for n in d['items'])")" "True"
"$VENV_PY" "$GRANT_ADMIN" viewer@example.com --revoke > /dev/null 2>&1
check "交還站務身分後回到非站務" "$(call GET /api/admin/overview '' "$JAR_HUMAN")" "404"

echo
if [ "$FAIL" -eq 0 ]; then
  printf "\033[32m== 全部通過：%d / %d ==\033[0m\n" "$PASS" "$((PASS + FAIL))"
else
  printf "\033[31m== %d 通過 / %d 失敗 ==\033[0m\n" "$PASS" "$FAIL"
fi
[ "$FAIL" -eq 0 ]
