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

from .models import Notification

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
        existing = db.scalar(
            select(Notification.id).where(
                Notification.user_id == recipient_id,
                Notification.actor_id == actor_id,
                Notification.kind == kind,
                Notification.post_id == post_id,
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
    return note


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
