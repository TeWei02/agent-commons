"""參與者名冊。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import User
from ..schemas import UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[UserOut])
def list_users(
    kind: Optional[str] = Query(None, description="human | agent"),
    limit: int = Query(50, ge=1, le=100),
    db: OrmSession = Depends(get_db),
):
    stmt = select(User)
    if kind in {"human", "agent"}:
        stmt = stmt.where(User.kind == kind)
    rows = db.scalars(stmt.order_by(User.id.asc()).limit(limit)).all()
    return [UserOut.model_validate(u) for u in rows]


@router.get("/{handle}", response_model=UserOut)
def get_user(handle: str, db: OrmSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None:
        raise HTTPException(status_code=404, detail="找不到這位參與者")
    return UserOut.model_validate(user)
