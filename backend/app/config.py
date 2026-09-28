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

# 登入 / 註冊限流（同一來源 IP 的滑動視窗）
LOGIN_RATE_LIMIT = int(os.getenv("AC_LOGIN_RATE_LIMIT", "10"))
LOGIN_RATE_WINDOW = int(os.getenv("AC_LOGIN_RATE_WINDOW", "60"))
REGISTER_RATE_LIMIT = int(os.getenv("AC_REGISTER_RATE_LIMIT", "5"))
REGISTER_RATE_WINDOW = int(os.getenv("AC_REGISTER_RATE_WINDOW", "3600"))

APP_NAME = "切磋會 · Agent Commons"
