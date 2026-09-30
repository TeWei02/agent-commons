"""即時推播端點：把站內通知以 Server-Sent Events 推給還開著頁面的瀏覽器。

為什麼是 SSE 而不是 WebSocket：切磋會只需要「伺服器 → 瀏覽器」單向提醒，
SSE 走的就是普通 HTTP，Cloudflare 隧道、反向代理（`--proxy-headers`）都不必
額外設定；斷線由瀏覽器內建的 EventSource 自動重連，前端不必自己寫重連邏輯。

認證沿用同一顆 Session Cookie，所以不需要在前端另外傳憑證；`?token=` 只是
留給命令列工具（`curl -N`）與測試用的備援入口。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from .. import events
from ..config import SESSION_COOKIE
from ..deps import Viewer, current_user, user_from_token

router = APIRouter(prefix="/api/live", tags=["live"])

# 心跳：沒有事件時每 15 秒送一行註解，避免中間的代理把連線當閒置切掉
HEARTBEAT_SECONDS = 15.0
# 前端 EventSource 的重連間隔提示（毫秒）
RETRY_MS = 3000


def _frame(event: str, payload: dict) -> str:
    """一則 SSE 訊息。data 只放單行 JSON，避免多行 data 的拼接歧義。"""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"


def _resolve_viewer(request: Request, token: Optional[str]) -> Optional[Viewer]:
    """Cookie 優先（瀏覽器走這條），其次才看 query 參數（命令列工具）。"""
    return user_from_token(request.cookies.get(SESSION_COOKIE) or token)


async def _event_stream(user: Viewer, request: Request) -> AsyncIterator[str]:
    queue = events.subscribe(user.id)
    try:
        yield f"retry: {RETRY_MS}\n\n"
        yield _frame("ready", {"handle": user.handle})
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            yield _frame(str(payload.get("type") or "notification"), payload)
    finally:
        events.unsubscribe(user.id, queue)


@router.get("/stream")
async def stream(
    request: Request,
    token: Optional[str] = Query(None, max_length=128),
):
    """訂閱即時通知。未登入一律 401，不提供匿名頻道。"""
    viewer = _resolve_viewer(request, token)
    if viewer is None:
        return StreamingResponse(
            iter([_frame("error", {"detail": "請先登入"})]),
            status_code=401,
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _event_stream(viewer, request),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # 有些反向代理會緩衝，明講這是串流
            "Content-Encoding": "identity",
        },
    )


@router.get("/status")
def status(user: User = Depends(current_user)):
    """目前有幾條連線在聽。前端用來顯示「即時」燈號，也方便維運排查。"""
    return {
        "ok": True,
        "mine": events.subscriber_count(user.id),
        "total": events.subscriber_count(),
    }
