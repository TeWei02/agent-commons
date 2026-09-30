"""站內即時推播（Server-Sent Events）。

切磋會的規模不需要訊息佇列，這裡只用「每位登入者一個記憶體佇列」把通知即時
推到還開著頁面的瀏覽器。三個刻意的設計：

1. **交易成功才送**：事件的產生點在 `notify.push()`，但只先暫存在
   `session.info`；等這個 Session `after_commit` 才真正廣播。回滾掉的操作
   不會推出幽靈通知，接收端看到的每一則都真的寫進資料庫了。
2. **推不出去就算了**：佇列滿了（瀏覽器卡住、來不及讀）直接丟掉最新一則。
   即時推播是加值路徑，不能因為推不動而拖慢發文／回應的交易。
3. **單 worker 前提**：訂閱者清單在進程記憶體，和 SQLite 單 worker 的部署
   假設一致。多 worker 要改用 Redis pub/sub，這點列在 README 的已知限制。

前端拿到事件後仍然會回呼 `/api/auth/me` 重取未讀數，因此事件本身只是「提醒」，
不承載關鍵狀態，掉了也不會漏資料。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import event
from sqlalchemy.orm import Session as OrmSession

# 同一位使用者可能同時開著多個分頁／裝置，各自一條佇列
_subscribers: Dict[int, Set[asyncio.Queue]] = defaultdict(set)

# 送事件的路由是同步函式（跑在 threadpool），要回到事件圈才能在佇列上放東西
_loop: Optional[asyncio.AbstractEventLoop] = None

_PENDING_KEY = "ac_pending_events"

# 單一連線積壓上限：滿了就丟，寧可少一則提醒也不要無限成長
QUEUE_SIZE = 64


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """記下服務所在的事件圈（lifespan 啟動時呼叫一次）。"""
    global _loop
    _loop = loop


def subscriber_count(user_id: Optional[int] = None) -> int:
    if user_id is not None:
        return len(_subscribers.get(user_id) or ())
    return sum(len(queues) for queues in _subscribers.values())


def subscribe(user_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    _subscribers[user_id].add(queue)
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue) -> None:
    queues = _subscribers.get(user_id)
    if not queues:
        return
    queues.discard(queue)
    if not queues:
        _subscribers.pop(user_id, None)


def _offer(queue: asyncio.Queue, payload: Dict[str, Any]) -> None:
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:  # pragma: no cover - 需要極端慢的接收端
        pass


def publish(user_id: int, payload: Dict[str, Any]) -> int:
    """把一則事件送給該使用者的所有連線，回傳實際投遞的連線數。"""
    queues = list(_subscribers.get(user_id) or ())
    if not queues or _loop is None:
        return 0

    delivered = 0
    for queue in queues:
        try:
            _loop.call_soon_threadsafe(_offer, queue, payload)
        except RuntimeError:  # pragma: no cover - 事件圈已關閉（服務正在收攤）
            break
        delivered += 1
    return delivered


def queue_event(db: OrmSession, user_id: int, payload: Dict[str, Any]) -> None:
    """掛在交易上的事件，等 commit 後才送（見 install）。"""
    db.info.setdefault(_PENDING_KEY, []).append((user_id, payload))


def _drain(session: OrmSession) -> List[Tuple[int, Dict[str, Any]]]:
    return list(session.info.pop(_PENDING_KEY, []))


def flush(session: OrmSession) -> None:
    for user_id, payload in _drain(session):
        publish(user_id, payload)


def install(session_cls: type = OrmSession) -> None:
    """把「commit 後送出、rollback 後丟掉」掛到 Session 類別上。

    只掛一次：測試會反覆啟動應用（每個 TestClient 一次 lifespan），重複註冊
    會讓同一則事件被送多次。
    """
    if getattr(session_cls, "_ac_events_installed", False):
        return
    session_cls._ac_events_installed = True

    @event.listens_for(session_cls, "after_commit")
    def _after_commit(session: OrmSession) -> None:  # pragma: no cover - 事件掛鉤
        flush(session)

    @event.listens_for(session_cls, "after_rollback")
    def _after_rollback(session: OrmSession) -> None:  # pragma: no cover - 事件掛鉤
        _drain(session)


def _iter_payloads(payloads: Iterable[Tuple[int, Dict[str, Any]]]) -> Iterable[Dict[str, Any]]:
    """測試輔助：只取事件內容。"""
    for _user_id, payload in payloads:
        yield payload
