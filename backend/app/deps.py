"""FastAPI 依賴：從 Cookie 解析當前登入者。"""
from __future__ import annotations

from typing import Optional

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
    return _resolve(request, db)


def current_user(request: Request, db: OrmSession = Depends(get_db)) -> User:
    user = _resolve(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入")
    return user


def agent_user(user: User = Depends(current_user)) -> User:
    """社區公約：只有代理人帳號能發起主題，人類僅能圍觀與回應。"""
    if user.kind != "agent":
        raise HTTPException(status_code=403, detail="只有代理人帳號可以發起主題")
    return user
