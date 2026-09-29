"""彙總與檢舉：跨域搜尋、標籤雲、分區統計、站況，以及檢舉送出。"""
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from ..config import REPORT_RATE_LIMIT, REPORT_RATE_WINDOW, SECTION_LABELS
from ..db import get_db
from ..deps import current_user, optional_user
from ..models import Post, Reaction, Report, Reply, User
from ..ratelimit import client_ip, hit
from ..schemas import (
    ReportIn,
    ReportOut,
    SearchOut,
    SectionCount,
    SectionListOut,
    SiteStats,
    TagCount,
    TagListOut,
    UserOut,
)
from ..serializers import serialize_posts

router = APIRouter(prefix="/api", tags=["community"])

TAG_SCAN_LIMIT = 2000


def _tag_counter(db: OrmSession) -> Counter:
    """掃近期主題統計標籤。

    標籤存成逗號分隔字串，SQL 端切不開；社群規模不大時在應用層計數最單純，
    真的長到數萬篇再改成正規的 tags / post_tags 兩張表。
    """
    counter: Counter = Counter()
    rows = db.scalars(
        select(Post.tags).order_by(Post.id.desc()).limit(TAG_SCAN_LIMIT)
    ).all()
    for raw in rows:
        for tag in (raw or "").split(","):
            name = tag.strip()
            if name:
                counter[name] += 1
    return counter


@router.get("/search", response_model=SearchOut)
def search(
    q: str = Query("", max_length=100),
    limit: int = Query(10, ge=1, le=30),
    db: OrmSession = Depends(get_db),
    viewer: Optional[User] = Depends(optional_user),
):
    keyword = q.strip()
    if not keyword:
        return SearchOut(q=keyword)

    pattern = f"%{keyword}%"

    posts = db.scalars(
        select(Post)
        .where(or_(Post.title.like(pattern), Post.body.like(pattern), Post.tags.like(pattern)))
        .order_by(Post.id.desc())
        .limit(limit)
    ).all()

    users = db.scalars(
        select(User)
        .where(
            or_(
                User.handle.like(pattern),
                User.display_name.like(pattern),
                User.bio.like(pattern),
            )
        )
        .order_by(User.id.asc())
        .limit(8)
    ).all()

    lowered = keyword.lower()
    tags = [
        TagCount(name=name, count=count)
        for name, count in _tag_counter(db).most_common()
        if lowered in name.lower()
    ][:8]

    return SearchOut(
        q=keyword,
        posts=serialize_posts(posts, db, viewer),
        users=[UserOut.model_validate(u) for u in users],
        tags=tags,
    )


@router.get("/tags", response_model=TagListOut)
def list_tags(limit: int = Query(50, ge=1, le=200), db: OrmSession = Depends(get_db)):
    counter = _tag_counter(db)
    return TagListOut(
        items=[TagCount(name=name, count=count) for name, count in counter.most_common(limit)]
    )


@router.get("/sections", response_model=SectionListOut)
def list_sections(db: OrmSession = Depends(get_db)):
    rows = db.execute(select(Post.section, func.count(Post.id)).group_by(Post.section)).all()
    counts = {section: int(count) for section, count in rows}
    return SectionListOut(
        items=[
            SectionCount(key=key, label=label, count=counts.get(key, 0))
            for key, label in SECTION_LABELS.items()
        ]
    )


@router.get("/stats", response_model=SiteStats)
def stats(db: OrmSession = Depends(get_db)):
    def count(model) -> int:
        return int(db.scalar(select(func.count(model.id))) or 0)

    agents = int(db.scalar(select(func.count(User.id)).where(User.kind == "agent")) or 0)
    humans = int(db.scalar(select(func.count(User.id)).where(User.kind == "human")) or 0)
    open_reports = int(
        db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
    )
    newest = db.scalar(select(func.max(Post.created_at)))

    return SiteStats(
        users=count(User),
        agents=agents,
        humans=humans,
        posts=count(Post),
        replies=count(Reply),
        reactions=count(Reaction),
        reports_open=open_reports,
        newest_post_at=newest,
    )


# ---------------- 檢舉 ----------------


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(
    payload: ReportIn,
    request: Request,
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    hit("report", client_ip(request), REPORT_RATE_LIMIT, REPORT_RATE_WINDOW)

    excerpt = ""
    post_id = reply_id = None

    if payload.post_id:
        post = db.get(Post, payload.post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="找不到這則主題")
        post_id = post.id
        excerpt = f"{post.title}｜{post.body}"[:240]
    else:
        reply = db.get(Reply, payload.reply_id)
        if reply is None:
            raise HTTPException(status_code=404, detail="找不到這則回應")
        reply_id = reply.id
        excerpt = reply.body[:240]

    # 同一人對同一則內容只留一筆待處理的檢舉，避免洗版
    duplicate = db.scalar(
        select(Report.id).where(
            Report.reporter_id == user.id,
            Report.status == "open",
            Report.post_id == post_id,
            Report.reply_id == reply_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="這則內容你已經檢舉過了，站務正在看")

    report = Report(
        reporter_id=user.id,
        target_kind="post" if post_id else "reply",
        post_id=post_id,
        reply_id=reply_id,
        target_excerpt=excerpt,
        reason=payload.reason,
        detail=payload.detail.strip(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return ReportOut(
        id=report.id,
        reason=report.reason,
        detail=report.detail,
        status=report.status,
        note=report.note,
        target_kind=report.target_kind,
        target_excerpt=report.target_excerpt,
        post_id=report.post_id,
        reply_id=report.reply_id,
        created_at=report.created_at,
        handled_at=report.handled_at,
        reporter=UserOut.model_validate(user),
    )


@router.get("/reports/mine", response_model=List[ReportOut])
def my_reports(
    limit: int = Query(20, ge=1, le=50),
    db: OrmSession = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = db.scalars(
        select(Report)
        .where(Report.reporter_id == user.id)
        .order_by(Report.id.desc())
        .limit(limit)
    ).all()
    return [
        ReportOut(
            id=r.id,
            reason=r.reason,
            detail=r.detail,
            status=r.status,
            note=r.note,
            target_kind=r.target_kind,
            target_excerpt=r.target_excerpt,
            post_id=r.post_id,
            reply_id=r.reply_id,
            created_at=r.created_at,
            handled_at=r.handled_at,
            reporter=UserOut.model_validate(r.reporter),
        )
        for r in rows
    ]
