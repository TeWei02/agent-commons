"""邀請碼：產生、正規化、核銷、狀態判定。

為什麼要有：開放註冊等於「誰知道網址誰就能進來」。邀請碼把開門的權利
交回站務手上——而且不必一次決定全站開或關，逐碼控制次數與期限就好。

三個入口共用這裡的邏輯，避免規則漂移：
- API：`routers/admin.py`（後台產生 / 列表 / 撤銷）、`routers/auth.py`（註冊核銷）
- CLI：`scripts/invite.py`
- 單元測試：`tests/test_invites.py`
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .db import utcnow
from .models import Invite, User

# 去掉容易看錯的 I / O / 0 / 1，方便口頭轉述與手抄
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_RE = re.compile(r"^[A-Z0-9]{6,32}$")

# 狀態代號（前端直接拿這個值配文案，不要在兩邊各寫一套判斷）
ACTIVE = "active"
USED_UP = "used_up"
EXPIRED = "expired"
REVOKED = "revoked"


class InviteError(Exception):
    """邀請碼不合法。訊息寫成可以直接顯示給註冊者看的句子。"""


def normalize(code: str) -> str:
    """去掉連字號、空白並轉大寫：`ac-abcd-efgh` 與 `ABCDEFGH` 等價。"""
    return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()


def format_code(code: str) -> str:
    """顯示用：每 4 碼插一個連字號，長碼念起來不容易斷錯。"""
    text = normalize(code)
    return "-".join(text[i : i + 4] for i in range(0, len(text), 4))


def new_code(length: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(max(6, min(32, length))))


def status_of(invite: Invite, now: Optional[datetime] = None) -> str:
    """active / used_up / expired / revoked。撤銷優先於其他狀態。"""
    if invite.revoked_at is not None:
        return REVOKED
    if invite.expires_at is not None and invite.expires_at < (now or utcnow()):
        return EXPIRED
    if invite.used_count >= invite.max_uses:
        return USED_UP
    return ACTIVE


def remaining_uses(invite: Invite) -> int:
    return max(0, invite.max_uses - invite.used_count)


def create(
    db: OrmSession,
    *,
    code: Optional[str] = None,
    note: str = "",
    max_uses: int = 1,
    days: Optional[int] = None,
    created_by: Optional[User] = None,
    length: int = 8,
    commit: bool = True,
) -> Invite:
    """產生一組邀請碼。`code` 有帶就沿用（匯入既有碼用），撞號會直接報錯。

    `days` 為 None 表示不過期；`max_uses` 至少 1。
    """
    desired = normalize(code) if code else ""
    if code and not CODE_RE.match(desired):
        raise InviteError("邀請碼只能用英數，長度 6–32")

    candidate = desired
    if not candidate:
        for _ in range(16):
            candidate = new_code(length)
            if db.scalar(select(Invite.id).where(Invite.code == candidate)) is None:
                break
        else:  # pragma: no cover - 8 碼空間下幾乎不可能走到
            raise InviteError("連續撞號，請再試一次")
    elif db.scalar(select(Invite.id).where(Invite.code == candidate)) is not None:
        raise InviteError("這組邀請碼已經存在")

    invite = Invite(
        code=candidate,
        note=(note or "").strip()[:120],
        max_uses=max(1, int(max_uses)),
        expires_at=utcnow() + timedelta(days=int(days)) if days else None,
        created_by_id=created_by.id if created_by is not None else None,
    )
    db.add(invite)
    if commit:
        db.commit()
        db.refresh(invite)
    else:
        db.flush()
    return invite


def find(db: OrmSession, raw_code: str) -> Optional[Invite]:
    """用使用者手上那串碼找紀錄（連字號、大小寫都不拘）。"""
    text = normalize(raw_code)
    if not text:
        return None
    return db.scalar(select(Invite).where(Invite.code == text))


def redeem(db: OrmSession, raw_code: str) -> Invite:
    """檢查並扣掉一次使用額度。失敗丟 InviteError。

    只改記憶體中的 used_count，不 commit——呼叫端把「扣額度」與
    「建立帳號」放進同一筆交易，註冊失敗時額度自然不會被吃掉。
    """
    if not normalize(raw_code):
        raise InviteError("這個站需要邀請碼，請向站務索取")

    invite = find(db, raw_code)
    if invite is None:
        raise InviteError("邀請碼不正確")

    state = status_of(invite)
    if state == REVOKED:
        raise InviteError("這組邀請碼已被站務撤銷")
    if state == EXPIRED:
        raise InviteError("這組邀請碼已過期")
    if state == USED_UP:
        raise InviteError("這組邀請碼的使用次數已用完")

    invite.used_count += 1
    return invite


def list_all(
    db: OrmSession,
    *,
    status: str = "",
    limit: int = 100,
) -> List[Invite]:
    """後台列表。新的排前面；status 有帶就只回該狀態。"""
    stmt = select(Invite).order_by(Invite.id.desc()).limit(max(1, min(500, limit)))
    rows = db.scalars(stmt).all()
    if status in {ACTIVE, USED_UP, EXPIRED, REVOKED}:
        rows = [row for row in rows if status_of(row) == status]
    return list(rows)


def revoke(db: OrmSession, invite: Invite, *, commit: bool = True) -> Invite:
    if invite.revoked_at is None:
        invite.revoked_at = utcnow()
        if commit:
            db.commit()
            db.refresh(invite)
    return invite
