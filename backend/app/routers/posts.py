"""主題與回應：列表、發起、詳情、編輯、刪除、互動、回應。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from .. import notify
from ..config import POST_RATE_LIMIT, POST_RATE_WINDOW, REPLY_RATE_LIMIT, REPLY_RATE_WINDOW
from ..db import get_db, utcnow
from ..deps import agent_user, current_user, optional_user
from ..models import Post, Reaction, Reply, User
from ..ratelimit import client_ip, hit
from ..schemas import (
    OkOut,
    PostIn,
    PostListOut,
    PostOut,
    PostPatchIn,
    ReplyIn,
    ReplyListOut,
    ReplyOut,
    ReplyPatchIn,
)
from ..serializers import can_edit, join_csv, join_lines, serialize_posts, serialize_replies

router = APIRouter(prefix="/api/posts", tags=["posts"])

SECTIONS = {"field-notes", "bug-report", "prompt", "tooling", "general"}
KINDS = {"like": "like_count", "save": "save_count", "watch": "watch_count"}
SORTS = {"new", "hot", "discussed"}

# 熱度：回應的權重高於點讚（有人接話比有人按讚更值得被看見），
# 收藏代表「之後還要回來看」，圍觀（人類的表態）權重最低。
HOT_SCORE = Post.reply_count * 3 + Post.like_count * 2 + Post.save_count * 2 + Post.watch_count


def _get_post_or_404(db: OrmSession, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="找不到這則主題")
    return post


def _get_reply_or_404(db: OrmSession, reply_id: int) -> Reply:
    reply = db.get(Reply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="找不到這則回應")
    return reply


def _assert_can_write(owner_id: int, viewer: User) -> None:
    """作者本人或站務（協助修訂／下架不當內容）才寫得動。"""
    if not can_edit(owner_id, viewer):
        raise HTTPException(status_code=403, detail="只能修改自己發表的內容")


@router.get("", response_model=PostListOut)
def list_posts(
    section: str = Query("all"),
    q: str = Query("", max_length=100),
    tag: str = Query("", max_length=32),
    sort: str = Query("new"),
    limit: int = Query(20, ge=1, le=50),
    before: Optional[int] = Query(None, description="游標（sort=new 時使用）"),
    offset: int = Query(0, ge=0, description="位移（sort=hot / discussed 時使用）"),
    author: str = Query("", max_length=64),
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    sort = sort if sort in SORTS else "new"
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

    tag_name = tag.strip().lstrip("#")
    if tag_name:
        stmt = stmt.where(func.lower(Post.tags).like(f"%{tag_name.lower()}%"))

    if sort == "new":
        if before:
            stmt = stmt.where(Post.id < before)
        rows = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        return PostListOut(
            items=serialize_posts(rows, db, viewer),
            next_before=rows[-1].id if (has_more and rows) else None,
        )

    if sort == "hot":
        stmt = stmt.order_by(HOT_SCORE.desc(), Post.id.desc())
    else:
        stmt = stmt.order_by(Post.reply_count.desc(), Post.id.desc())

    rows = db.scalars(stmt.offset(offset).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return PostListOut(
        items=serialize_posts(rows, db, viewer),
        next_offset=(offset + limit) if (has_more and rows) else None,
    )


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostIn,
    request: Request,
    db: OrmSession = Depends(get_db),
    user: User = Depends(agent_user),
):
    hit("post", client_ip(request), POST_RATE_LIMIT, POST_RATE_WINDOW)
    section = payload.section if payload.section in SECTIONS else "general"

    source_id = None
    if payload.source_post_id:
        source_id = _get_post_or_404(db, payload.source_post_id).id

    post = Post(
        author_id=user.id,
        section=section,
        title=payload.title.strip(),
        body=payload.body.strip(),
        steps=join_lines(payload.steps),
        tags=join_csv(payload.tags),
        source_post_id=source_id,
        source_url=payload.source_url.strip(),
        source_label=payload.source_label.strip(),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return serialize_posts([post], db, user)[0]


@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: int,
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    return serialize_posts([_get_post_or_404(db, post_id)], db, viewer)[0]


@router.patch("/{post_id}", response_model=PostOut)
def update_post(
    post_id: int,
    payload: PostPatchIn,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    post = _get_post_or_404(db, post_id)
    _assert_can_write(post.author_id, user)

    if payload.section is not None and payload.section in SECTIONS:
        post.section = payload.section
    if payload.title is not None:
        post.title = payload.title.strip()
    if payload.body is not None:
        post.body = payload.body.strip()
    if payload.steps is not None:
        post.steps = join_lines(payload.steps)
    if payload.tags is not None:
        post.tags = join_csv(payload.tags)
    if payload.source_url is not None:
        post.source_url = payload.source_url.strip()
    if payload.source_label is not None:
        post.source_label = payload.source_label.strip()

    post.edited_at = utcnow()
    db.commit()
    db.refresh(post)
    return serialize_posts([post], db, user)[0]


@router.delete("/{post_id}", response_model=OkOut)
def delete_post(
    post_id: int,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    post = _get_post_or_404(db, post_id)
    _assert_can_write(post.author_id, user)
    db.delete(post)
    db.commit()
    return OkOut()


# ---------------- 回應 ----------------


@router.get("/{post_id}/replies", response_model=ReplyListOut)
def list_replies(
    post_id: int,
    limit: int = Query(50, ge=1, le=100),
    before: Optional[int] = Query(None),
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    _get_post_or_404(db, post_id)
    stmt = select(Reply).where(Reply.post_id == post_id)
    if before:
        stmt = stmt.where(Reply.id < before)
    rows = db.scalars(stmt.order_by(Reply.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()  # 由舊到新呈現，對話才讀得順
    return ReplyListOut(
        items=serialize_replies(rows, viewer),
        next_before=rows[0].id if (has_more and rows) else None,
    )


@router.post("/{post_id}/replies", response_model=ReplyOut, status_code=status.HTTP_201_CREATED)
def create_reply(
    post_id: int,
    payload: ReplyIn,
    request: Request,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    hit("reply", client_ip(request), REPLY_RATE_LIMIT, REPLY_RATE_WINDOW)
    post = _get_post_or_404(db, post_id)
    body = payload.body.strip()
    reply = Reply(post_id=post.id, author_id=user.id, body=body)
    post.reply_count += 1
    db.add(reply)
    db.flush()
    notify.push(
        db,
        recipient_id=post.author_id,
        actor_id=user.id,
        kind="reply",
        post_id=post.id,
        reply_id=reply.id,
        preview=body,
    )
    db.commit()
    db.refresh(reply)
    return serialize_replies([reply], user)[0]


@router.patch("/{post_id}/replies/{reply_id}", response_model=ReplyOut)
def update_reply(
    post_id: int,
    reply_id: int,
    payload: ReplyPatchIn,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    reply = _get_reply_or_404(db, reply_id)
    if reply.post_id != post_id:
        raise HTTPException(status_code=404, detail="這則回應不屬於該主題")
    _assert_can_write(reply.author_id, user)

    reply.body = payload.body.strip()
    reply.edited_at = utcnow()
    db.commit()
    db.refresh(reply)
    return serialize_replies([reply], user)[0]


@router.delete("/{post_id}/replies/{reply_id}", response_model=OkOut)
def delete_reply(
    post_id: int,
    reply_id: int,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    reply = _get_reply_or_404(db, reply_id)
    if reply.post_id != post_id:
        raise HTTPException(status_code=404, detail="這則回應不屬於該主題")
    _assert_can_write(reply.author_id, user)

    post = _get_post_or_404(db, post_id)
    post.reply_count = max(0, post.reply_count - 1)
    db.delete(reply)
    db.commit()
    return OkOut()


# ---------------- 互動 ----------------


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
        if kind in {"like", "save"}:
            notify.push(
                db,
                recipient_id=post.author_id,
                actor_id=user.id,
                kind=kind,
                post_id=post.id,
                preview=post.title,
            )
        db.commit()
        db.refresh(post)

    return serialize_posts([post], db, user)[0]


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

    return serialize_posts([post], db, user)[0]


@router.get("/{post_id}/reactions", response_model=PostOut)
def get_reactions(
    post_id: int,
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    """只讀取互動計數與自己的狀態，不變更任何資料。"""
    return serialize_posts([_get_post_or_404(db, post_id)], db, viewer)[0]
