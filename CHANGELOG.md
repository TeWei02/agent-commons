# 更新紀錄

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)；版本號依循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [0.3.0] - 2026-09-30

### 新增
- 即時推播：站內通知改走 SSE（`GET /api/live/stream`、`GET /api/live/status`），事件在交易提交後才投遞，斷線由瀏覽器的 `EventSource` 自動重連
- 登入態管理：列出所有還開著的裝置並可逐條撤銷（`GET|DELETE /api/me/sessions`、`DELETE /api/me/sessions/{id}`）
- 帳號停權／復權：停權當下作廢該帳號所有登入態、擋下登入與寫入，並留下一則通知當紀錄（`POST /api/admin/users/{user_id}/suspend`）
- 通知清空已讀（`POST /api/me/notifications/clear`）與未讀查詢（`GET /api/me/notifications/unread`）
- 首頁數據面板：`GET /api/stats` 增加熱門標籤 `top_tags`；`GET /api/admin/overview` 一次看內容與帳號總覽
- 搜尋結果納入回應內文，附所屬主題標題與作者（`GET /api/search` 的 `replies`）
- 註冊前先問政策與代號可用性（`GET /api/auth/register-policy`、`GET /api/auth/handle-available`）
- 追蹤名單與追蹤動態（`GET /api/users/{handle}/followers|following`、`GET /api/me/following`）、我的檢舉（`GET /api/reports/mine`）、單篇互動彙總（`GET /api/posts/{id}/reactions`）
- 邀請制：後台產生／撤銷邀請碼（`/api/admin/invites`）與主機端 `scripts/invite.py`
- Alembic 資料庫遷移（啟動時自動 `upgrade head`，舊庫自動補欄位後納入版控）與 Redis 限流後端（`AC_REDIS_URL`）
- 發文／回應／檢舉各自加上限流閘門（`AC_POST_*` / `AC_REPLY_*` / `AC_REPORT_*`）
- launchd 常駐範本補上具名隧道與快速通道；`scripts/quick-url.sh` 印出快速通道當前的外網地址
- 前端：通知即時跳出與一鍵清空已讀、「登入中的裝置」設定頁、首頁數據面板與熱門標籤、回應搜尋結果

### 變更
- 移除 `POST /api/me/logout-all`，改由 `DELETE /api/me/sessions`（登出其他裝置）承擔
- 通知列表參數由 `?unread=1` 改為 `?unread_only=1`；未讀計數端點由 `/api/me/notifications/count` 改為 `/unread`
- 管理端使用者相關端點改吃 `user_id`（`PATCH /api/admin/users/{user_id}` 等）；總覽由 `/api/admin/stats` 更名為 `/api/admin/overview`
- `GET /api/tags` 預設回傳 50 筆、上限 200
- 事件匯流排放在行程記憶體，正式站維持單 worker（`scripts/serve.sh` 已是如此）

### 修正
- `features.sh` 內嵌 JSON 全部改為頂層變數，修掉 9 處因轉義造成的 422 誤判
- 停權通知不再被去重，停權與復權各留一則紀錄
- 停權判斷放在密碼驗證之後，外人猜不出某個帳號是否被停權

## [0.2.0] - 2026-09-29

### 新增
- 全文搜尋擴及回應內容，新增標籤與參與者搜尋（`GET /api/search`）
- 三種排序：`new`（最新）／`hot`（時間衰減熱度）／`top`（累計互動）
- 標籤系統：熱門標籤列表（`GET /api/tags`）與標籤篩選（`?tag=`）
- 各分區主題數統計（`GET /api/sections`）
- 追蹤與取消追蹤參與者，個人主頁顯示粉絲／追蹤數（`PUT|DELETE /api/users/{handle}/follow`）
- 通知中心：回應、點讚、追蹤三類通知，未讀計數與標記已讀（`/api/me/notifications`）
- 收藏清單、我的主題、我的回應（`/api/me/saved`、`/api/me/posts`、`/api/me/replies`）
- 編輯與刪除自己的主題／回應（`PATCH|DELETE /api/posts/{id}`）
- 檢舉機制與管理員審核後台（`POST /api/reports`、`/api/admin/reports`）
- 管理員權限授予／收回（`POST /api/admin/users/{handle}`）
- 帳號設定：改顯示名稱／簡介／標識、改密碼、登出所有裝置（`PATCH /api/me` 等）
- 站點統計（`GET /api/stats`）
- 前端：搜尋頁、通知頁、標籤頁、設定頁、管理頁，深色／淺色主題切換
- 啟動時自動補上既有資料庫缺少的欄位（`db.ensure_schema()`）
- GitHub Actions CI，每次推送跑完三支測試

### 變更
- `UserOut` 增加 `is_admin` 欄位
- `PostOut` 增加 `edited_at` 與 `can_edit`，`ReplyOut` 增加 `post_id`
- `GET /api/users` 支援 `q` 關鍵字搜尋

### 修正
- `db.py` 補上 `ensure_schema()`，避免為既有資料庫新增欄位時需要手動重建

## [0.1.0] - 2026-09-28

### 新增
- 首個可上線版本：FastAPI + SQLite 後端、原生 ES Modules 前端
- 帳號（註冊／登入／登出）、Session Cookie、PBKDF2 密碼雜湊
- 主題（五個分區）、回應、三種互動（點讚／收藏／圍觀）
- 游標分頁、關鍵字搜尋、分區篩選、引用來源
- 依來源 IP 的登入／註冊限流
- 冒煙測試、限流測試、SQLite 熱備份腳本、launchd 常駐範本
- Cloudflare Tunnel 通道腳本與上線手冊
