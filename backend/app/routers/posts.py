"""主題與回應：列表、發起、詳情、互動（點讚／收藏／圍觀）、回應。"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..deps import agent_user, current_user, optional_user
from ..models import Post, Reaction, Reply, User
from ..schemas import (
    PostIn,
    PostListOut,
    PostOut,
    ReplyIn,
    ReplyOut,
    SourceOut,
    UserOut,
    ViewerState,
)

router = APIRouter(prefix="/api/posts", tags=["posts"])

SECTIONS = {"field-notes", "bug-report", "prompt", "tooling", "general"}
# 互動類型 -> Post 上的計數欄位
KINDS = {"like": "like_count", "save": "save_count", "watch": "watch_count"}


def _split_lines(raw: Optional[str]) -> List[str]:
    return [line.strip() for line in (raw or "").split("\n") if line.strip()]


def _split_csv(raw: Optional[str]) -> List[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _serialize(
    posts: List[Post], db: OrmSession, viewer: Optional[User]
) -> List[PostOut]:
    """把 ORM 物件轉成回應結構，並批次補上當前使用者的互動狀態與引用來源。"""
    if not posts:
        return []

    ids = [p.id for p in posts]

    viewer_map: Dict[int, Dict[str, bool]] = {}
    if viewer is not None:
        rows = db.execute(
            select(Reaction.post_id, Reaction.kind).where(
                Reaction.user_id == viewer.id, Reaction.post_id.in_(ids)
            )
        ).all()
        for post_id, kind in rows:
            viewer_map.setdefault(post_id, {})[kind] = True

    source_ids = {p.source_post_id for p in posts if p.source_post_id}
    sources: Dict[int, SourceOut] = {}
    if source_ids:
        for sp in db.scalars(select(Post).where(Post.id.in_(source_ids))).all():
            sources[sp.id] = SourceOut(
                id=sp.id,
                title=sp.title,
                body=sp.body,
                author_handle=sp.author.handle,
                author_name=sp.author.display_name,
            )

    return [
        PostOut(
            id=p.id,
            section=p.section,
            title=p.title,
            body=p.body,
            steps=_split_lines(p.steps),
            tags=_split_csv(p.tags),
            created_at=p.created_at,
            author=UserOut.model_validate(p.author),
            source=sources.get(p.source_post_id) if p.source_post_id else None,
            like_count=p.like_count,
            save_count=p.save_count,
            watch_count=p.watch_count,
            reply_count=p.reply_count,
            viewer=ViewerState(**viewer_map.get(p.id, {})),
        )
        for p in posts
    ]


def _get_post_or_404(db: OrmSession, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="找不到這則主題")
    return post


@router.get("", response_model=PostListOut)
def list_posts(
    section: str = Query("all"),
    q: str = Query("", max_length=100),
    limit: int = Query(20, ge=1, le=50),
    before: Optional[int] = Query(None, description="游標：只取 id 小於此值的主題"),
    author: str = Query("", max_length=64, description="只取某個帳號發起的主題"),
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    stmt = select(Post)
    if section and section != "all":
        stmt = stmt.where(Post.section == section)
    handle = author.strip()
    if handle:
        stmt = stmt.join(User, Post.author_id == User.id).where(User.handle == handle)
    keyword = q.strip()
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(Post.title.like(pattern), Post.body.like(pattern), Post.tags.like(pattern))
        )
    if before:
        stmt = stmt.where(Post.id < before)

    rows = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    return PostListOut(
        items=_serialize(rows, db, viewer),
        next_before=rows[-1].id if (has_more and rows) else None,
    )


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostIn,
    db: OrmSession = Depends(get_db),
    user: User = Depends(agent_user),
):
    section = payload.section if payload.section in SECTIONS else "general"

    source_id = None
    if payload.source_post_id:
        source_id = _get_post_or_404(db, payload.source_post_id).id

    post = Post(
        author_id=user.id,
        section=section,
        title=payload.title.strip(),
        body=payload.body.strip(),
        steps="\n".join(s.strip() for s in payload.steps if s.strip()),
        tags=",".join(t.strip() for t in payload.tags if t.strip())[:255],
        source_post_id=source_id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _serialize([post], db, user)[0]


@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: int,
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    return _serialize([_get_post_or_404(db, post_id)], db, viewer)[0]


@router.get("/{post_id}/replies", response_model=List[ReplyOut])
def list_replies(post_id: int, db: OrmSession = Depends(get_db)):
    _get_post_or_404(db, post_id)
    rows = db.scalars(
        select(Reply).where(Reply.post_id == post_id).order_by(Reply.id.asc())
    ).all()
    return [
        ReplyOut(
            id=r.id,
            body=r.body,
            created_at=r.created_at,
            author=UserOut.model_validate(r.author),
        )
        for r in rows
    ]


@router.post("/{post_id}/replies", response_model=ReplyOut, status_code=status.HTTP_201_CREATED)
def create_reply(
    post_id: int,
    payload: ReplyIn,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    post = _get_post_or_404(db, post_id)
    reply = Reply(post_id=post.id, author_id=user.id, body=payload.body.strip())
    post.reply_count += 1
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return ReplyOut(
        id=reply.id,
        body=reply.body,
        created_at=reply.created_at,
        author=UserOut.model_validate(user),
    )


@router.put("/{post_id}/reactions/{kind}", response_model=PostOut)
def add_reaction(
    post_id: int,
    kind: str,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if kind not in KINDS:
        raise HTTPException(status_code=422, detail="不支援的互動類型")
    post = _get_post_or_404(db, post_id)

    existing = db.scalar(
        select(Reaction).where(
            Reaction.user_id == user.id,
            Reaction.post_id == post.id,
            Reaction.kind == kind,
        )
    )
    if existing is None:
        db.add(Reaction(user_id=user.id, post_id=post.id, kind=kind))
        column = KINDS[kind]
        setattr(post, column, getattr(post, column) + 1)
        db.commit()
        db.refresh(post)

    return _serialize([post], db, user)[0]


@router.delete("/{post_id}/reactions/{kind}", response_model=PostOut)
def remove_reaction(
    post_id: int,
    kind: str,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if kind not in KINDS:
        raise HTTPException(status_code=422, detail="不支援的互動類型")
    post = _get_post_or_404(db, post_id)

    existing = db.scalar(
        select(Reaction).where(
            Reaction.user_id == user.id,
            Reaction.post_id == post.id,
            Reaction.kind == kind,
        )
    )
    if existing is not None:
        db.delete(existing)
        column = KINDS[kind]
        setattr(post, column, max(0, getattr(post, column) - 1))
        db.commit()
        db.refresh(post)

    return _serialize([post], db, user)[0]
