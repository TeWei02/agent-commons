"""極輕量的記憶體滑動視窗限流，用來擋登入暴力破解與註冊灌水。

刻意不引入 Redis 依賴：單機、單 worker 的小型社群足夠用。
若之後要橫向擴充多個 worker / 多台機器，把 `hit()` 換成 Redis 的
INCR + EXPIRE 即可，呼叫端介面不用動。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import TRUST_PROXY_HEADERS

# (作用域, 身分) -> 命中時間戳佇列
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()

SWEEP_THRESHOLD = 2048
SWEEP_MAX_AGE = 3600.0


def client_ip(request: Request) -> str:
    """取得來源 IP；置於反向代理後方時需開啟 AC_TRUST_PROXY=1。"""
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    """偶發清理，避免長期運行後字典無限膨脹。呼叫端需已持鎖。"""
    if len(_hits) < SWEEP_THRESHOLD:
        return
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > SWEEP_MAX_AGE]:
        _hits.pop(key, None)


def hit(scope: str, identity: str, limit: int, window_seconds: int) -> None:
    """記一次嘗試。超過門檻即丟 429，並附上 Retry-After。"""
    now = time.monotonic()
    key = (scope, identity)
    with _lock:
        _sweep(now)
        queue = _hits[key]
        while queue and now - queue[0] > window_seconds:
            queue.popleft()
        if len(queue) >= limit:
            retry_after = int(window_seconds - (now - queue[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"嘗試過於頻繁，請於 {retry_after} 秒後再試",
                headers={"Retry-After": str(retry_after)},
            )
        queue.append(now)


def clear(scope: str, identity: str) -> None:
    """清掉某個身分的計數。

    登入成功時歸零，避免正常使用者因為自己手誤幾次、之後被視窗卡住；
    對暴力破解沒有影響（猜錯的次數照樣累計）。
    """
    with _lock:
        _hits.pop((scope, identity), None)


def reset() -> None:
    """清空所有計數。測試或後台解鎖時使用。"""
    with _lock:
        _hits.clear()
