"""當前使用者的個人操作：資料維護、改密碼、收藏、我的回應、通知。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import notify
from ..config import SESSION_COOKIE
from ..db import get_db, utcnow
from ..deps import current_user
from ..models import Follow, Notification, Post, Reaction, Reply, Session, User
from ..schemas import (
    ClearedOut,
    NotificationListOut,
    OkOut,
    PasswordIn,
    PostListOut,
    ProfileIn,
    ReplyListOut,
    SessionListOut,
    SessionOut,
    UnreadOut,
    UserOut,
)
from ..security import hash_password, hash_token, verify_password
from ..serializers import serialize_notifications, serialize_posts, serialize_replies

router = APIRouter(prefix="/api/me", tags=["me"])


@router.patch("", response_model=UserOut)
def update_profile(
    payload: ProfileIn,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.bio is not None:
        user.bio = payload.bio.strip()
    if payload.mark_key is not None:
        user.mark_key = payload.mark_key
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/password", response_model=OkOut)
def change_password(
    payload: PasswordIn,
    request: Request,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    # 由管理員代開的代理人帳號可能沒有密碼，此時不強制驗舊密碼
    if user.password_hash and not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="目前的密碼不正確")
    user.password_hash = hash_password(payload.new_password)
    _drop_other_sessions(db, user, _current_token(request))
    db.commit()
    return OkOut()


@router.get("/saved", response_model=PostListOut)
def saved_posts(
    limit: int = Query(20, ge=1, le=50),
    before: Optional[int] = Query(None),
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """收藏過的主題。以互動表的 id 當游標，收藏順序即時間順序。"""
    stmt = (
        select(Post)
        .join(Reaction, Reaction.post_id == Post.id)
        .where(Reaction.user_id == user.id, Reaction.kind == "save")
    )
    if before:
        stmt = stmt.where(Post.id < before)
    rows = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return PostListOut(
        items=serialize_posts(rows, db, user),
        next_before=rows[-1].id if (has_more and rows) else None,
    )


@router.get("/replies", response_model=ReplyListOut)
def my_replies(
    limit: int = Query(30, ge=1, le=100),
    before: Optional[int] = Query(None),
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Reply).where(Reply.author_id == user.id)
    if before:
        stmt = stmt.where(Reply.id < before)
    rows = db.scalars(stmt.order_by(Reply.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ReplyListOut(
        items=serialize_replies(rows, user),
        next_before=rows[-1].id if (has_more and rows) else None,
    )


@router.get("/following", response_model=PostListOut)
def following_feed(
    limit: int = Query(20, ge=1, le=50),
    before: Optional[int] = Query(None),
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """只看追蹤對象發起的主題。"""
    stmt = (
        select(Post)
        .join(Follow, Follow.followee_id == Post.author_id)
        .where(Follow.follower_id == user.id)
    )
    if before:
        stmt = stmt.where(Post.id < before)
    rows = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return PostListOut(
        items=serialize_posts(rows, db, user),
        next_before=rows[-1].id if (has_more and rows) else None,
    )


# ---------------- 通知 ----------------


@router.get("/notifications", response_model=NotificationListOut)
def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.id.desc()).limit(limit)).all()
    return NotificationListOut(
        items=serialize_notifications(rows, db),
        unread=notify.unread_count(db, user.id),
    )


@router.get("/notifications/unread", response_model=UnreadOut)
def unread(db: OrmSession = Depends(get_db), user: User = Depends(current_user)):
    return UnreadOut(unread=notify.unread_count(db, user.id))


@router.post("/notifications/read", response_model=UnreadOut)
def mark_read(
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """全部標為已讀。逐則已讀在此社群規模下沒有必要。"""
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).all()
    if rows:
        now = utcnow()
        for row in rows:
            row.read_at = now
        db.commit()
    return UnreadOut(unread=0)


@router.post("/notifications/clear", response_model=ClearedOut)
def clear_read(
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """清掉已讀通知。

    只刪已讀的：未讀的通知一旦被清掉，使用者永遠不知道自己錯過了什麼，
    那是資料遺失而不是「清理」。要減少未讀，請先標為已讀。
    """
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_not(None)
        )
    ).all()
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
    return ClearedOut(removed=len(rows))


# ---------------- 登入態 ----------------


def _current_token(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


def _drop_other_sessions(db: OrmSession, user: User, keep_token: Optional[str]) -> int:
    """踢掉這個帳號的其他登入態，留下目前這一個。回傳踢掉幾條。"""
    stmt = select(Session).where(Session.user_id == user.id)
    if keep_token:
        stmt = stmt.where(Session.token_hash != hash_token(keep_token))
    rows = db.scalars(stmt).all()
    for row in rows:
        db.delete(row)
    return len(rows)


@router.get("/sessions", response_model=SessionListOut)
def list_sessions(
    request: Request,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """目前這個帳號還開著哪些登入態。只給時間與編號，不吐 token（資料庫也沒存）。"""
    keep = _current_token(request)
    keep_hash = hash_token(keep) if keep else ""
    rows = db.scalars(
        select(Session).where(Session.user_id == user.id).order_by(Session.id.desc())
    ).all()
    items = [
        SessionOut(
            id=row.id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            current=bool(keep_hash) and row.token_hash == keep_hash,
        )
        for row in rows
    ]
    return SessionListOut(items=items, total=len(items))


@router.delete("/sessions", response_model=ClearedOut)
def revoke_other_sessions(
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """「登出其他裝置」：留下現在這台，其餘全部失效。"""
    removed = _drop_other_sessions(db, user, _current_token(request))
    if removed:
        db.commit()
    return ClearedOut(removed=removed)


@router.delete("/sessions/{session_id}", response_model=ClearedOut)
def revoke_session(
    session_id: int,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """撤銷單一條登入態。撤到自己這條時，順便把 Cookie 清掉。"""
    row = db.get(Session, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="找不到這條登入態")

    token = _current_token(request)
    is_current = bool(token) and row.token_hash == hash_token(token)
    db.delete(row)
    db.commit()
    if is_current:
        response.delete_cookie(key=SESSION_COOKIE, path="/")
    return ClearedOut(removed=1)
