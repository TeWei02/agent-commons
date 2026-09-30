"""站內通知的寫入。

規則很簡單，但有三件事必須守住：
1. 不通知自己（自己回應自己的主題不需要提示）。
2. 同一人對同一篇的同一種動作只留一則，避免連點洗版。
3. `preview` 是給列表直接顯示的短句，寫入時就截好，讀取端不必再查關聯表。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from . import events
from .models import Notification, User
from .schemas import UserOut

PREVIEW_LIMIT = 80


def _clip(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat[:PREVIEW_LIMIT] + ('…' if len(flat) > PREVIEW_LIMIT else "")


def push(
    db: OrmSession,
    *,
    recipient_id: Optional[int],
    actor_id: int,
    kind: str,
    post_id: Optional[int] = None,
    reply_id: Optional[int] = None,
    preview: str = "",
    once: bool = True,
) -> Optional[Notification]:
    """寫一則通知。`once=True` 時同（人, 類型, 主題）只保留最早的一則。

    呼叫端負責 commit；這裡只 add，讓通知與觸發它的動作落在同一個交易裡。
    """
    if recipient_id is None or recipient_id == actor_id:
        return None

    if once:
        # post_id 可能是 NULL（與主題無關的通知），而 `= NULL` 在 SQL 裡永遠不成立，
        # 得改用 IS NULL，否則同一種動作會被重複寫入。
        same_post = (
            Notification.post_id.is_(None) if post_id is None else Notification.post_id == post_id
        )
        existing = db.scalar(
            select(Notification.id).where(
                Notification.user_id == recipient_id,
                Notification.actor_id == actor_id,
                Notification.kind == kind,
                same_post,
            )
        )
        if existing is not None:
            return None

    note = Notification(
        user_id=recipient_id,
        actor_id=actor_id,
        kind=kind,
        post_id=post_id,
        reply_id=reply_id,
        preview=_clip(preview),
    )
    db.add(note)

    # 即時推播：只排進交易，commit 成功後 events 才會真的送出去（見 events.py）。
    events.queue_event(db, recipient_id, _event(db, note, kind, actor_id))
    return note


def _event(db: OrmSession, note: Notification, kind: str, actor_id: int) -> dict:
    """推給瀏覽器的事件內容。只帶畫面需要的欄位，前端收到後仍會回呼 /api/auth/me。"""
    payload: dict = {
        "type": "notification",
        "kind": kind,
        "preview": note.preview,
        "post_id": note.post_id,
    }
    actor = db.get(User, actor_id)
    if actor is not None:
        payload["actor"] = UserOut.model_validate(actor).model_dump(mode="json")
    return payload


def unread_count(db: OrmSession, user_id: int) -> int:
    from sqlalchemy import func

    return int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )
