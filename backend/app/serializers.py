"""ORM 物件 -> 對外結構的轉換。

集中在一處的理由：同一則主題會出現在動態廣場、搜尋、個人主頁、收藏清單，
若各處各自拼裝，遲早會出現「某個列表少了 edited_at」這種前後端不一致。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .models import Notification, Post, Reaction, Reply, User
from .schemas import NotificationOut, PostOut, ReplyOut, SourceOut, UserOut, ViewerState


def split_lines(raw: Optional[str]) -> List[str]:
    return [line.strip() for line in (raw or "").split("\n") if line.strip()]


def split_csv(raw: Optional[str]) -> List[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def join_lines(items: Iterable[str]) -> str:
    return "\n".join(item.strip() for item in items if item and item.strip())


def join_csv(items: Iterable[str]) -> str:
    cleaned = [item.strip().lstrip("#") for item in items if item and item.strip()]
    # 去重但保留輸入順序
    seen, ordered = set(), []
    for tag in cleaned:
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(tag)
    return ",".join(ordered)[:255]


def can_edit(owner_id: int, viewer: Optional[User]) -> bool:
    """作者本人或站務人員才能改動內容。"""
    if viewer is None:
        return False
    return viewer.id == owner_id or bool(viewer.is_admin)


def _viewer_map(db: OrmSession, post_ids: List[int], viewer: Optional[User]):
    if viewer is None or not post_ids:
        return {}
    rows = db.execute(
        select(Reaction.post_id, Reaction.kind).where(
            Reaction.user_id == viewer.id, Reaction.post_id.in_(post_ids)
        )
    ).all()
    result: Dict[int, Dict[str, bool]] = {}
    for post_id, kind in rows:
        result.setdefault(post_id, {})[kind] = True
    return result


def serialize_posts(posts: List[Post], db: OrmSession, viewer: Optional[User]) -> List[PostOut]:
    if not posts:
        return []

    viewers = _viewer_map(db, [p.id for p in posts], viewer)

    source_ids = {p.source_post_id for p in posts if p.source_post_id}
    sources: Dict[int, SourceOut] = {}
    if source_ids:
        for row in db.scalars(select(Post).where(Post.id.in_(source_ids))).all():
            sources[row.id] = SourceOut(
                id=row.id,
                title=row.title,
                body=row.body,
                author_handle=row.author.handle,
                author_name=row.author.display_name,
            )

    return [
        PostOut(
            id=p.id,
            section=p.section,
            title=p.title,
            body=p.body,
            steps=split_lines(p.steps),
            tags=split_csv(p.tags),
            created_at=p.created_at,
            edited_at=p.edited_at,
            author=UserOut.model_validate(p.author),
            source=sources.get(p.source_post_id) if p.source_post_id else None,
            source_url=p.source_url or "",
            source_label=p.source_label or "",
            like_count=p.like_count,
            save_count=p.save_count,
            watch_count=p.watch_count,
            reply_count=p.reply_count,
            viewer=ViewerState(**viewers.get(p.id, {})),
            can_edit=can_edit(p.author_id, viewer),
        )
        for p in posts
    ]


def serialize_replies(replies: List[Reply], viewer: Optional[User]) -> List[ReplyOut]:
    return [
        ReplyOut(
            id=r.id,
            post_id=r.post_id,
            body=r.body,
            created_at=r.created_at,
            edited_at=r.edited_at,
            author=UserOut.model_validate(r.author),
            can_edit=can_edit(r.author_id, viewer),
        )
        for r in replies
    ]


def serialize_notifications(notes: List[Notification], db: OrmSession) -> List[NotificationOut]:
    if not notes:
        return []

    post_ids = {n.post_id for n in notes if n.post_id}
    titles: Dict[int, str] = {}
    if post_ids:
        for post_id, title in db.execute(
            select(Post.id, Post.title).where(Post.id.in_(post_ids))
        ).all():
            titles[post_id] = title

    return [
        NotificationOut(
            id=n.id,
            kind=n.kind,
            preview=n.preview,
            post_id=n.post_id,
            post_title=titles.get(n.post_id) if n.post_id else None,
            read=n.read_at is not None,
            created_at=n.created_at,
            actor=UserOut.model_validate(n.actor),
        )
        for n in notes
    ]
