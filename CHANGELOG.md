# 更新紀錄

格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)；版本號依循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

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
