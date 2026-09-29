"""滑動視窗限流，用來擋登入暴力破解與註冊灌水。

兩種後端，呼叫端介面完全相同：

- **記憶體**（預設）：單 worker 的部署這樣就夠，不多一個外部依賴。
- **Redis**：設定 `AC_REDIS_URL` 後啟用。計數放在 Redis，多個 worker
  或多台機器共用同一份，`AC_WORKERS>1` 時才真的擋得住。

Redis 連不上時自動退回記憶體並印出警告，不會讓整個站掛掉。
"""
from __future__ import annotations

import threading
import time
import uuid
import warnings
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import RATE_LIMIT_PREFIX, REDIS_URL, TRUST_PROXY_HEADERS

SWEEP_THRESHOLD = 2048
SWEEP_MAX_AGE = 3600.0


def client_ip(request: Request) -> str:
    """取得來源 IP；置於反向代理後方時需開啟 AC_TRUST_PROXY=1。"""
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class MemoryBackend:
    """進程記憶體滑動視窗。"""

    name = "memory"

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _sweep(self, now: float) -> None:
        """偶發清理，避免長期運行後字典無限膨脹。呼叫端需已持鎖。"""
        if len(self._hits) < SWEEP_THRESHOLD:
            return
        for key in [k for k, q in self._hits.items() if not q or now - q[-1] > SWEEP_MAX_AGE]:
            self._hits.pop(key, None)

    def hit(self, key: tuple[str, str], limit: int, window_seconds: int) -> int | None:
        """記一次嘗試；未超限回 None，超限回建議的等待秒數。"""
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            queue = self._hits[key]
            while queue and now - queue[0] > window_seconds:
                queue.popleft()
            if len(queue) >= limit:
                return int(window_seconds - (now - queue[0])) + 1
            queue.append(now)
            return None

    def clear(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisBackend:
    """用 Redis ZSET 做的滑動視窗。

    每次檢查先移除視窗外的成員（score 是毫秒時間戳），再數剩下的。
    成員名稱帶亂數，避免同一毫秒內的多筆嘗試互相覆蓋。
    """

    name = "redis"

    def __init__(self, url: str, prefix: str, client=None) -> None:
        if client is None:
            import redis  # 只有真的要連 Redis 時才需要這個套件

            client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        self._redis = client
        self._prefix = prefix

    def _key(self, key: tuple[str, str]) -> str:
        return f"{self._prefix}:{key[0]}:{key[1]}"

    def hit(self, key: tuple[str, str], limit: int, window_seconds: int) -> int | None:
        redis_key = self._key(key)
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - window_seconds * 1000

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff_ms)
        pipe.zcard(redis_key)
        _, count = pipe.execute()

        if count >= limit:
            oldest = self._redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                release_ms = int(oldest[0][1]) + window_seconds * 1000
                return max(1, int((release_ms - now_ms) / 1000) + 1)
            return max(1, window_seconds)

        pipe = self._redis.pipeline()
        pipe.zadd(redis_key, {f"{now_ms}-{uuid.uuid4().hex[:8]}": now_ms})
        pipe.expire(redis_key, window_seconds + 1)
        pipe.execute()
        return None

    def clear(self, key: tuple[str, str]) -> None:
        self._redis.delete(self._key(key))

    def reset(self) -> None:
        """只清掉自己前綴底下的鍵，不動 Redis 上的其他資料。"""
        for redis_key in self._redis.scan_iter(match=f"{self._prefix}:*", count=200):
            self._redis.delete(redis_key)


_backend = None
_backend_lock = threading.Lock()


def _build_backend():
    if not REDIS_URL:
        return MemoryBackend()
    try:
        backend = RedisBackend(REDIS_URL, RATE_LIMIT_PREFIX)
        backend._redis.ping()
    except Exception as exc:  # 連不上就別讓服務起不來
        warnings.warn(f"Redis 限流後端不可用（{exc}），改用進程記憶體限流。", stacklevel=2)
        return MemoryBackend()
    print(f"[ratelimit] 使用 Redis 後端（前綴 {RATE_LIMIT_PREFIX}）")
    return backend


def backend():
    """目前的限流後端（延遲建立）。"""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = _build_backend()
    return _backend


def use_backend(instance) -> None:
    """換掉限流後端。測試用（例如注入 fakeredis），正式流程不需要呼叫。"""
    global _backend
    _backend = instance


def hit(scope: str, identity: str, limit: int, window_seconds: int) -> None:
    """記一次嘗試。超過門檻即丟 429，並附上 Retry-After。"""
    key = (scope, identity)
    current = backend()
    try:
        retry_after = current.hit(key, limit, window_seconds)
    except Exception as exc:
        # Redis 中途掛掉：退回記憶體，至少本機還能擋
        if isinstance(current, RedisBackend):
            warnings.warn(f"Redis 限流失敗（{exc}），暫時改用進程記憶體。", stacklevel=2)
            fallback = MemoryBackend()
            use_backend(fallback)
            retry_after = fallback.hit(key, limit, window_seconds)
        else:
            raise

    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"嘗試過於頻繁，請於 {retry_after} 秒後再試",
            headers={"Retry-After": str(retry_after)},
        )


def clear(scope: str, identity: str) -> None:
    """清掉某個身分的計數。

    登入成功時歸零，避免正常使用者因為自己手誤幾次、之後被視窗卡住；
    對暴力破解沒有影響（猜錯的次數照樣累計）。
    """
    backend().clear((scope, identity))


def reset() -> None:
    """清空所有計數。測試或後台解鎖時使用。"""
    backend().reset()
