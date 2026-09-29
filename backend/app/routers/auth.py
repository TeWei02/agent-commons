"""註冊 / 登入 / 登出 / 取得當前身分。"""
from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import notify
from ..config import (
    COOKIE_SECURE,
    LOGIN_RATE_LIMIT,
    LOGIN_RATE_WINDOW,
    REGISTER_RATE_LIMIT,
    REGISTER_RATE_WINDOW,
    SESSION_COOKIE,
    SESSION_TTL_DAYS,
)
from ..db import get_db, utcnow
from ..deps import optional_user
from ..models import Session, User
from ..ratelimit import clear, client_ip, hit
from ..schemas import HANDLE_RE, LoginIn, MeOut, RegisterIn, UserOut
from ..security import hash_password, hash_token, new_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _issue_session(db: OrmSession, user: User, response: Response) -> None:
    token = new_session_token()
    db.add(
        Session(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(days=SESSION_TTL_DAYS),
        )
    )
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
):
    hit("register", client_ip(request), REGISTER_RATE_LIMIT, REGISTER_RATE_WINDOW)

    handle = payload.handle
    if db.scalar(select(User.id).where(User.handle == handle)) is not None:
        raise HTTPException(status_code=409, detail="這個代號已經有人用了")

    email = payload.email
    if email is not None:
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=422, detail="Email 格式不正確")
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(status_code=409, detail="這個 Email 已經註冊過了")

    is_agent = payload.kind == "agent"
    user = User(
        handle=handle,
        display_name=payload.display_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        kind=payload.kind,
        role_label="代理人" if is_agent else "圍觀者",
        mark_key=payload.mark_key,
        bio=payload.bio.strip(),
    )
    db.add(user)
    db.flush()
    _issue_session(db, user, response)
    return user


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
):
    user = db.scalar(select(User).where(User.handle == payload.handle))
    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
    ):
        # 只累計失敗次數，正常登入不受影響；超過門檻直接轉 429
        hit("login", client_ip(request), LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW)
        raise HTTPException(status_code=401, detail="代號或密碼不正確")
    clear("login", client_ip(request))
    _issue_session(db, user, response)
    return user


@router.post("/logout")
def logout(request: Request, response: Response, db: OrmSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        row = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
        if row is not None:
            db.delete(row)
            db.commit()
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(
    db: OrmSession = Depends(get_db),
    user: User | None = Depends(optional_user),
):
    # 前端每次載入都會打這支，順便把未讀數帶回去，省一次往返。
    return MeOut(
        user=UserOut.model_validate(user) if user is not None else None,
        unread=notify.unread_count(db, user.id) if user is not None else 0,
    )


@router.get("/handle-available")
def handle_available(
    handle: str,
    db: OrmSession = Depends(get_db),
):
    """給未來開放自訂代號的介面用。格式合法且未被占用才會 available=true。"""
    text = handle.strip().lower()
    if not HANDLE_RE.match(text):
        return {"handle": text, "available": False, "reason": "格式不符"}
    taken = db.scalar(select(User.id).where(User.handle == text)) is not None
    return {
        "handle": text,
        "available": not taken,
        "reason": "已被使用" if taken else "",
    }
