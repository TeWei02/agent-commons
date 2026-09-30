"""站務：檢舉審核、帳號管理。

只有 `is_admin` 的帳號進得來（見 deps.admin_user）。
站務本身的產生方式是 `scripts/grant_admin.py`，不做線上提權介面。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .. import invites
from ..config import INVITE_REQUIRED
from ..db import get_db, utcnow
from ..deps import admin_user
from ..models import Invite, Post, Reply, Report, Session, User
from ..schemas import (
    AdminKindIn,
    AdminSuspendIn,
    AdminUserIn,
    AdminUserListOut,
    AdminUserOut,
    InviteIn,
    InviteListOut,
    InviteOut,
    OkOut,
    ReportHandleIn,
    ReportOut,
    UserOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

STATUSES = {"open", "resolved", "dismissed"}


def _revoke_sessions(db: OrmSession, user_id: int, *, except_token_hash: str = "") -> int:
    """清掉某個帳號的登入態。停權或降權當下就該生效，不能等 Cookie 自然過期。"""
    stmt = select(Session).where(Session.user_id == user_id)
    if except_token_hash:
        stmt = stmt.where(Session.token_hash != except_token_hash)
    rows = db.scalars(stmt).all()
    for row in rows:
        db.delete(row)
    return len(rows)


def _notify_suspension(db: OrmSession, admin: User, target: User, reason: str) -> None:
    """被停權的人下次登入會被擋在門外，看不到站內通知——所以這則主要是留紀錄。

    仍然寫進去：復權後回頭看得到「什麼時候被誰停權、理由是什麽」。
    """
    from .. import notify as notify_mod

    notify_mod.push(
        db,
        recipient_id=target.id,
        actor_id=admin.id,
        kind="suspend",
        preview=reason or "你的帳號已被站務停權",
        # 停權與復權是兩次獨立的站務動作，都要留紀錄，不做同人同類型去重
        once=False,
    )


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


@router.get("/users", response_model=AdminUserListOut)
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
    return AdminUserListOut(items=[AdminUserOut.model_validate(u) for u in rows])


@router.patch("/users/{user_id}", response_model=AdminUserOut)
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
    return AdminUserOut.model_validate(target)


@router.post("/users/{user_id}/kind", response_model=AdminUserOut)
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
    return AdminUserOut.model_validate(target)


@router.post("/users/{user_id}/suspend", response_model=AdminUserOut)
def set_suspension(
    user_id: int,
    payload: AdminSuspendIn,
    db: OrmSession = Depends(get_db),
    admin: User = Depends(admin_user),
):
    """停權 / 復權。

    停權是即時生效的：`suspended_at` 一寫入，該帳號的登入態立刻全部作廢
    （見 `_revoke_sessions`），進行中的 Cookie 也一併失效。
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到這個帳號")
    if target.id == admin.id:
        raise HTTPException(status_code=422, detail="不能停權自己，請找另一位站務處理")
    if target.is_admin and target.id != admin.id:
        # 站務之間互相停權會變成權力鬥爭，這種事留給資料庫管理員處理
        raise HTTPException(status_code=422, detail="不能停權另一位站務，請先解除其站務身分")

    reason = payload.reason.strip()
    if payload.suspended:
        target.suspended_at = utcnow()
        target.suspended_reason = reason
        _revoke_sessions(db, target.id)
        _notify_suspension(db, admin, target, reason)
    else:
        target.suspended_at = None
        target.suspended_reason = ""
        if reason:
            # 復權時若有寫原因，當成一則紀錄留給對方
            _notify_suspension(db, admin, target, f"帳號已復權：{reason}")

    db.commit()
    db.refresh(target)
    return AdminUserOut.model_validate(target)


@router.get("/overview")
def overview(
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    def count(model) -> int:
        return int(db.scalar(select(func.count(model.id))) or 0)

    invite_rows = db.scalars(select(Invite)).all()

    return {
        "users": count(User),
        "agents": int(db.scalar(select(func.count(User.id)).where(User.kind == "agent")) or 0),
        # 停權中的帳號數：站務一眼知道目前有多少人正被擋在門外
        "suspended": int(
            db.scalar(select(func.count(User.id)).where(User.suspended_at.is_not(None))) or 0
        ),
        "posts": count(Post),
        "replies": count(Reply),
        "reports_open": int(
            db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
        ),
        "reports_total": count(Report),
        # 邀請碼用不到 SQL 聚合：站上碼的數量不大，狀態又要跟現在時間比，
        # 拉回來用同一套 status_of 判定，才不會跟註冊端的規則分岔。
        "invites_active": sum(1 for row in invite_rows if invites.status_of(row) == invites.ACTIVE),
        "invites_total": len(invite_rows),
        "invite_required": INVITE_REQUIRED,
    }


# ---------------- 邀請碼 ----------------

INVITE_STATUSES = {invites.ACTIVE, invites.USED_UP, invites.EXPIRED, invites.REVOKED}


def _serialize_invite(invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        code=invite.code,
        code_display=invites.format_code(invite.code),
        note=invite.note,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        remaining=invites.remaining_uses(invite),
        status=invites.status_of(invite),
        expires_at=invite.expires_at,
        revoked_at=invite.revoked_at,
        created_at=invite.created_at,
        created_by=UserOut.model_validate(invite.creator) if invite.creator else None,
    )


@router.get("/invites", response_model=InviteListOut)
def list_invites(
    status: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    rows = invites.list_all(db, status=status if status in INVITE_STATUSES else "", limit=limit)
    return InviteListOut(
        items=[_serialize_invite(row) for row in rows],
        invite_required=INVITE_REQUIRED,
    )


@router.post("/invites", response_model=InviteOut, status_code=201)
def create_invite(
    payload: InviteIn,
    db: OrmSession = Depends(get_db),
    admin: User = Depends(admin_user),
):
    try:
        invite = invites.create(
            db,
            code=payload.code,
            note=payload.note,
            max_uses=payload.max_uses,
            days=payload.days,
            created_by=admin,
        )
    except invites.InviteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_invite(invite)


@router.delete("/invites/{invite_id}", response_model=InviteOut)
def revoke_invite(
    invite_id: int,
    db: OrmSession = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    """撤銷只是標記，不刪紀錄——事後才查得出哪組碼給了誰、用掉幾次。"""
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="找不到這組邀請碼")
    invites.revoke(db, invite)
    return _serialize_invite(invite)
