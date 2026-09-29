"""限流後端單元測試。

兩種後端跑同一套期待，Redis 那邊用 fakeredis 當替身，不需要真的開一台 Redis。
多出來的「跨實例共用計數」是 Redis 後端存在的理由：多 worker 時記憶體版本擋不住。

執行：
    cd backend && .venv/bin/python tests/test_ratelimit_redis.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fakeredis  # noqa: E402

from app.ratelimit import MemoryBackend, RedisBackend  # noqa: E402

PREFIX = "ac:rl:test"
PASSED = 0


def check(label: str, condition: bool) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"✗ {label}")
    PASSED += 1
    print(f"  ✓ {label}")


def fake_client() -> "fakeredis.FakeStrictRedis":
    return fakeredis.FakeStrictRedis(decode_responses=True)


def redis_backend(client) -> RedisBackend:
    return RedisBackend("redis://unused", PREFIX, client=client)


def shared_expectations(name: str, backend) -> None:
    """兩種後端都該有的行為。"""
    key = ("login", "1.2.3.4")

    for _ in range(2):
        check(f"{name}｜未達門檻放行", backend.hit(key, 2, 60) is None)

    retry_after = backend.hit(key, 2, 60)
    check(
        f"{name}｜超限被擋並附上等待秒數",
        retry_after is not None and 1 <= retry_after <= 61,
    )

    backend.clear(key)
    check(f"{name}｜clear 後歸零", backend.hit(key, 2, 60) is None)

    backend.reset()
    check(
        f"{name}｜不同 scope 分開計數",
        backend.hit(("register", "1.2.3.4"), 1, 60) is None
        and backend.hit(("login", "1.2.3.4"), 1, 60) is None,
    )

    backend.reset()
    check(f"{name}｜不同來源分開計數", backend.hit(("login", "5.6.7.8"), 1, 60) is None)

    backend.reset()
    check(f"{name}｜視窗內首次放行", backend.hit(("login", "9.9.9.9"), 1, 1) is None)
    check(f"{name}｜視窗內再次被擋", backend.hit(("login", "9.9.9.9"), 1, 1) is not None)
    time.sleep(1.05)
    check(f"{name}｜視窗過後重新放行", backend.hit(("login", "9.9.9.9"), 1, 1) is None)


def memory_suite() -> None:
    shared_expectations("記憶體", MemoryBackend())


def redis_suite() -> None:
    shared_expectations("Redis", redis_backend(fake_client()))

    print("\n[Redis｜多 worker 共用同一份計數]")
    client = fake_client()
    worker_a = redis_backend(client)
    worker_b = redis_backend(client)
    key = ("login", "10.0.0.7")
    check("worker A 第 1 次放行", worker_a.hit(key, 2, 60) is None)
    check("worker B 第 2 次放行", worker_b.hit(key, 2, 60) is None)
    check("worker A 第 3 次被擋（看到 B 的計數）", worker_a.hit(key, 2, 60) is not None)

    print("\n[Redis｜reset 只清自己的前綴]")
    client.set("someone:else", "keep-me")
    backend = redis_backend(client)
    backend.hit(("login", "10.0.0.8"), 1, 60)
    backend.reset()
    check("自己的鍵已清空", not list(client.scan_iter(match=f"{PREFIX}:*")))
    check("別人的鍵沒被動到", client.get("someone:else") == "keep-me")


def main() -> int:
    print("[記憶體後端｜與 Redis 相同的行為期待]")
    memory_suite()
    print("\n[Redis 後端｜與記憶體相同的行為期待]")
    redis_suite()
    print(f"\n全部通過：{PASSED} 項")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
