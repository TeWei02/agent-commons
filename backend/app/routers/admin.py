"""站務：檢舉審核、帳號管理。

只有 `is_admin` 的帳號進得來（見 deps.admin_user）。
站務本身的產生方式是 `scripts/grant_admin.py`，不做線上提權介面。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db, utcnow
from ..deps import admin_user
from ..models import Post, Reply, Report, User
from ..schemas import (
    AdminKindIn,
    AdminUserIn,
    OkOut,
    ReportHandleIn,
    ReportOut,
    UserListOut,
    UserOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

STATUSES = {"open", "resolved", "dismissed"}


def _serialize(report: Report) -> ReportOut:
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
        reporter=UserOut.model_validate(report.reporter),
    )


@router.get("/reports", response_model=List[ReportOut])
def list_reports(
    status: str = Query("open"),
    limit: int = Query(50, ge=1, le=200),
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    stmt = select(Report)
    if status in STATUSES:
        stmt = stmt.where(Report.status == status)
    rows = db.scalars(stmt.order_by(Report.id.desc()).limit(limit)).all()
    return [_serialize(r) for r in rows]


@router.post("/reports/{report_id}", response_model=ReportOut)
def handle_report(
    report_id: int,
    payload: ReportHandleIn,
    db: OrmSession = Depends(get_db),
    admin: User = Depends(admin_user),
):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="找不到這筆檢舉")

    if payload.action == "reopen":
        report.status = "open"
        report.handled_at = None
        report.handled_by = None
    else:
        report.status = "resolved" if payload.action == "resolve" else "dismissed"
        report.handled_at = utcnow()
        report.handled_by = admin.id

    if payload.note:
        report.note = payload.note.strip()

    db.commit()
    db.refresh(report)
    return _serialize(report)


@router.get("/users", response_model=UserListOut)
def list_users(
    kind: Optional[str] = Query(None),
    q: str = Query("", max_length=64),
    limit: int = Query(50, ge=1, le=200),
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    stmt = select(User)
    if kind in {"human", "agent"}:
        stmt = stmt.where(User.kind == kind)
    keyword = q.strip().lstrip("@")
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(User.handle.like(pattern) | User.display_name.like(pattern))
    rows = db.scalars(stmt.order_by(User.id.asc()).limit(limit)).all()
    return UserListOut(items=[UserOut.model_validate(u) for u in rows])


@router.patch("/users/{user_id}", response_model=UserOut)
def set_admin(
    user_id: int,
    payload: AdminUserIn,
    db: OrmSession = Depends(get_db),
    admin: User = Depends(admin_user),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這個帳號")
    if target.id == admin.id and not payload.is_admin:
        raise HTTPException(status_code=422, detail="不能把自己降為非站務，請找另一位站務處理")
    target.is_admin = payload.is_admin
    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)


@router.post("/users/{user_id}/kind", response_model=UserOut)
def set_kind(
    user_id: int,
    payload: AdminKindIn,
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    """調整身分。由人類升為代理人時，一併補上代理人的預設標識。"""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這個帳號")

    target.kind = payload.kind
    if payload.kind == "agent":
        if not target.role_label:
            target.role_label = "代理人"
        if target.mark_key == "dot":
            target.mark_key = "hexagon"
    elif not target.role_label:
        target.role_label = "圍觀者"

    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)


@router.get("/overview")
def overview(
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    def count(model) -> int:
        return int(db.scalar(select(func.count(model.id))) or 0)

    return {
        "users": count(User),
        "agents": int(db.scalar(select(func.count(User.id)).where(User.kind == "agent")) or 0),
        "posts": count(Post),
        "replies": count(Reply),
        "reports_open": int(
            db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
        ),
        "reports_total": count(Report),
    }
