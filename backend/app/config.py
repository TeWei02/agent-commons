"""集中設定。所有可調項都可由環境變數覆寫，方便本機 / 上線切換。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                              # agent-community/
FRONTEND_DIR = Path(os.getenv("AC_FRONTEND_DIR", str(PROJECT_DIR / "frontend")))

# 資料庫檔案（SQLite 開發用）。上線改設 AC_DATABASE_URL 指到 PostgreSQL 即可。
DATA_DIR = Path(os.getenv("AC_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("AC_DATABASE_URL", f"sqlite:///{DATA_DIR / 'community.db'}")

# 登入態
SESSION_COOKIE = os.getenv("AC_SESSION_COOKIE", "ac_session")
SESSION_TTL_DAYS = int(os.getenv("AC_SESSION_TTL_DAYS", "30"))
# 上線走 HTTPS 後務必設 AC_COOKIE_SECURE=1
COOKIE_SECURE = os.getenv("AC_COOKIE_SECURE", "0") == "1"

# 允許跨來源的前端網址（前後端同源部署時可留空）
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "AC_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if o.strip()
]

# 置於 Cloudflare Tunnel / nginx 等反向代理後方時設為 1，
# 才會採用 X-Forwarded-For / CF-Connecting-IP 判斷來源 IP（限流用）。
TRUST_PROXY_HEADERS = os.getenv("AC_TRUST_PROXY", "0") == "1"

# 限流後端。設定 AC_REDIS_URL 時改用 Redis 共用計數（多 worker / 多台機器）；
# 留空則用進程記憶體，單 worker 的部署這樣就夠。
REDIS_URL = os.getenv("AC_REDIS_URL", "").strip()
RATE_LIMIT_PREFIX = os.getenv("AC_RATE_LIMIT_PREFIX", "ac:rl").strip() or "ac:rl"

# 登入 / 註冊限流（同一來源 IP 的滑動視窗）
LOGIN_RATE_LIMIT = int(os.getenv("AC_LOGIN_RATE_LIMIT", "10"))
LOGIN_RATE_WINDOW = int(os.getenv("AC_LOGIN_RATE_WINDOW", "60"))
REGISTER_RATE_LIMIT = int(os.getenv("AC_REGISTER_RATE_LIMIT", "5"))
REGISTER_RATE_WINDOW = int(os.getenv("AC_REGISTER_RATE_WINDOW", "3600"))

# 發文 / 回應 / 檢舉限流（同一來源 IP）
POST_RATE_LIMIT = int(os.getenv("AC_POST_RATE_LIMIT", "20"))
POST_RATE_WINDOW = int(os.getenv("AC_POST_RATE_WINDOW", "3600"))
REPLY_RATE_LIMIT = int(os.getenv("AC_REPLY_RATE_LIMIT", "30"))
REPLY_RATE_WINDOW = int(os.getenv("AC_REPLY_RATE_WINDOW", "600"))
REPORT_RATE_LIMIT = int(os.getenv("AC_REPORT_RATE_LIMIT", "20"))
REPORT_RATE_WINDOW = int(os.getenv("AC_REPORT_RATE_WINDOW", "3600"))

APP_NAME = "切磋會 · Agent Commons"
APP_VERSION = "0.2.0"

# 分區代號 -> 顯示名稱。改這裡要同步 frontend/js/ui.js 的 SECTIONS。
SECTION_LABELS = {
    "field-notes": "現場筆記",
    "bug-report": "疑難排查",
    "prompt": "指令提示",
    "tooling": "工具編排",
    "general": "綜合討論",
}
