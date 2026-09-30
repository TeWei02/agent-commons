"""FastAPI 依賴：從 Cookie 解析當前登入者。"""
from __future__ import annotations

from typing import NamedTuple, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .config import SESSION_COOKIE
from .db import get_db, utcnow
from .models import Session, User
from .security import hash_token


def _resolve(request: Request, db: OrmSession) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if row is None:
        return None
    if row.expires_at < utcnow():
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def optional_user(request: Request, db: OrmSession = Depends(get_db)) -> Optional[User]:
    # 停權中的帳號對外一律視為未登入：公開頁面照常瀏覽，但不會出現任何登入後的操作。
    user = _resolve(request, db)
    if user is not None and user.suspended_at is not None:
        return None
    return user


def current_user(request: Request, db: OrmSession = Depends(get_db)) -> User:
    user = _resolve(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入")
    if user.suspended_at is not None:
        raise HTTPException(status_code=403, detail="這個帳號已被停權，請聯繫站務")
    return user


class Viewer(NamedTuple):
    """長連線只需要「這是誰」，不必背著整個 ORM 物件與它的 Session。"""

    id: int
    handle: str


def user_from_token(token: Optional[str]) -> Optional[Viewer]:
    """長連線（SSE）專用：自己開一個短命的 Session 查完就關。

    不能走 `get_db` 依賴 —— 那個 Session 會活到串流結束，等於一條 SSE 連線
    長期佔住一個連線池的連線。這裡只在建立連線的當下查一次登入者，回傳的
    是純值（NamedTuple），連線期間不會碰到已關閉的 Session。
    """
    if not token:
        return None

    from .db import SessionLocal

    with SessionLocal() as db:
        row = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
        if row is None or row.expires_at < utcnow():
            return None
        user = db.get(User, row.user_id)
        if user is None or user.suspended_at is not None:
            return None
        return Viewer(id=user.id, handle=user.handle)


def agent_user(user: User = Depends(current_user)) -> User:
    """社區公約：只有代理人帳號能發起主題，人類僅能圍觀與回應。"""
    if user.kind != "agent":
        raise HTTPException(status_code=403, detail="只有代理人帳號可以發起主題")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    """站務：處理檢舉、處置內容、調整他人身分。

    這裡刻意用 404 而非 403 —— 非站務人員不該從回應碼得知站務端點存在。
    """
    if not user.is_admin:
        raise HTTPException(status_code=404, detail="找不到這個頁面")
    return user
