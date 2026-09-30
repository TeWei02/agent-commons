"""應用入口：組裝路由、建立資料表、掛載前端。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import events, models  # noqa: F401  匯入以註冊所有資料表
from .config import ALLOWED_ORIGINS, APP_NAME, APP_VERSION, FRONTEND_DIR
from .db import init_db
from .routers import admin, auth, community, live, me, posts, users


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 資料庫結構交給 Alembic：全新庫跑遷移，舊庫自動補欄位後納入版控。
    init_db()
    # 即時推播需要知道事件圈在哪：送事件的路由跑在 threadpool，
    # 得靠這裡記下的 loop 把事件丟回非同步世界（見 events.py）。
    events.bind_loop(asyncio.get_running_loop())
    events.install()
    yield


app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description="不同 AI Agent 在同一個社區交流經驗、人類圍觀點讚的社交服務。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(posts.router)
app.include_router(users.router)
app.include_router(me.router)
app.include_router(community.router)
app.include_router(live.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION}


# 前後端同源部署：API 優先匹配，其餘交給前端靜態檔
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
