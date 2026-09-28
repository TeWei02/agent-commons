"""應用入口：組裝路由、建立資料表、掛載前端。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  匯入以註冊所有資料表
from .config import ALLOWED_ORIGINS, APP_NAME, FRONTEND_DIR
from .db import Base, engine
from .routers import auth, posts, users


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 上線改用 Alembic 遷移；這裡負責首次啟動時自動建表
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=f"{APP_NAME} API",
    version="0.1.0",
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


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "app": APP_NAME}


# 前後端同源部署：API 優先匹配，其餘交給前端靜態檔
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
