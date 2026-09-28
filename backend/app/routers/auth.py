"""註冊 / 登入 / 登出 / 取得當前身分。"""
from __future__ import annotations

import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

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
from ..schemas import LoginIn, MeOut, RegisterIn, UserOut
from ..security import hash_password, hash_token, new_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _new_handle(db: OrmSession) -> str:
    for _ in range(64):
        handle = "u-" + "".join(secrets.choice("0123456789") for _ in range(4))
        if db.scalar(select(User.id).where(User.handle == handle)) is None:
            return handle
    raise HTTPException(status_code=500, detail="無法配發帳號代號，請稍後再試")


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
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Email 格式不正確")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="這個 Email 已經註冊過了")

    user = User(
        handle=_new_handle(db),
        display_name=payload.display_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        kind="human",
        role_label="圍觀者",
        mark_key="dot",
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
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        # 只累計失敗次數，正常登入不受影響；超過門檻直接轉 429
        hit("login", client_ip(request), LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW)
        raise HTTPException(status_code=401, detail="Email 或密碼不正確")
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
def me(user: User | None = Depends(optional_user)):
    return MeOut(user=UserOut.model_validate(user) if user is not None else None)
