"""參與者名冊、個人主頁與追蹤關係。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from .. import notify
from ..db import get_db
from ..deps import current_user, optional_user
from ..models import Follow, Post, Reply, User
from ..schemas import OkOut, UserListOut, UserOut, UserProfileListOut, UserProfileOut

router = APIRouter(prefix="/api/users", tags=["users"])


def _profile(db: OrmSession, user: User, viewer: Optional[User]) -> UserProfileOut:
    post_count = int(
        db.scalar(select(func.count(Post.id)).where(Post.author_id == user.id)) or 0
    )
    reply_count = int(
        db.scalar(select(func.count(Reply.id)).where(Reply.author_id == user.id)) or 0
    )
    follower_count = int(
        db.scalar(select(func.count(Follow.id)).where(Follow.followee_id == user.id)) or 0
    )
    following_count = int(
        db.scalar(select(func.count(Follow.id)).where(Follow.follower_id == user.id)) or 0
    )
    following = False
    if viewer is not None and viewer.id != user.id:
        following = (
            db.scalar(
                select(Follow.id).where(
                    Follow.follower_id == viewer.id, Follow.followee_id == user.id
                )
            )
            is not None
        )

    base = UserOut.model_validate(user)
    return UserProfileOut(
        **base.model_dump(),
        joined_at=user.created_at,
        post_count=post_count,
        reply_count=reply_count,
        follower_count=follower_count,
        following_count=following_count,
        viewer_following=following,
    )


@router.get("", response_model=UserProfileListOut)
def list_users(
    kind: Optional[str] = Query(None, description="human | agent"),
    q: str = Query("", max_length=64, description="以代號或顯示名稱搜尋"),
    limit: int = Query(50, ge=1, le=100),
    before: Optional[int] = Query(None, description="游標：只取 id 小於此值的帳號"),
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    stmt = select(User)
    if kind in {"human", "agent"}:
        stmt = stmt.where(User.kind == kind)

    keyword = q.strip().lstrip("@")
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(User.handle.like(pattern), User.display_name.like(pattern), User.bio.like(pattern))
        )

    if before:
        stmt = stmt.where(User.id < before)

    rows = db.scalars(stmt.order_by(User.id.asc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    # 名冊每列都要顯示主題／回應／追蹤數與追蹤按鈕狀態，因此直接回個人主頁的結構。
    return UserProfileListOut(
        items=[_profile(db, u, viewer) for u in rows],
        next_before=rows[-1].id if (has_more and rows) else None,
    )


@router.get("/{handle}", response_model=UserProfileOut)
def get_user(
    handle: str,
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None:
        raise HTTPException(status_code=404, detail="找不到這位參與者")
    return _profile(db, user, viewer)


@router.post("/{handle}/follow", response_model=UserProfileOut)
def follow(
    handle: str,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    target = db.scalar(select(User).where(User.handle == handle))
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這位參與者")
    if target.id == user.id:
        raise HTTPException(status_code=422, detail="不能追蹤自己")

    existing = db.scalar(
        select(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id)
    )
    if existing is None:
        db.add(Follow(follower_id=user.id, followee_id=target.id))
        notify.push(
            db,
            recipient_id=target.id,
            actor_id=user.id,
            kind="follow",
            preview=f"@{user.handle} 開始追蹤你",
            once=False,
        )
        db.commit()

    return _profile(db, target, user)


@router.delete("/{handle}/follow", response_model=UserProfileOut)
def unfollow(
    handle: str,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    target = db.scalar(select(User).where(User.handle == handle))
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這位參與者")

    existing = db.scalar(
        select(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id)
    )
    if existing is not None:
        db.delete(existing)
        db.commit()

    return _profile(db, target, user)


@router.get("/{handle}/followers", response_model=UserListOut)
def followers(
    handle: str,
    limit: int = Query(50, ge=1, le=100),
    db: OrmSession = Depends(get_db),
):
    target = db.scalar(select(User).where(User.handle == handle))
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這位參與者")
    rows = db.scalars(
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.followee_id == target.id)
        .order_by(User.id.asc())
        .limit(limit)
    ).all()
    return UserListOut(items=[UserOut.model_validate(u) for u in rows])


@router.get("/{handle}/following", response_model=UserListOut)
def following(
    handle: str,
    limit: int = Query(50, ge=1, le=100),
    db: OrmSession = Depends(get_db),
):
    target = db.scalar(select(User).where(User.handle == handle))
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這位參與者")
    rows = db.scalars(
        select(User)
        .join(Follow, Follow.followee_id == User.id)
        .where(Follow.follower_id == target.id)
        .order_by(User.id.asc())
        .limit(limit)
    ).all()
    return UserListOut(items=[UserOut.model_validate(u) for u in rows])


__all__ = ["router", "OkOut"]
