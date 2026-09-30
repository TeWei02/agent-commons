"""站內即時推播（SSE）與通知掛勾的單元測試。

不需要起服務：直接對 app.events 的訂閱／投遞／交易掛勾下斷言，外加
app.live 的訊息框格式。這條路徑沒有外部依賴，壞掉只會在瀏覽器端安靜地少一則
提醒——所以規則要靠這裡釘住。

執行：
    cd backend && .venv/bin/python tests/test_events.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 用臨時資料庫，不碰開發庫；必須在 import app.db 之前設好
_TMP_DIR = tempfile.mkdtemp(prefix="ac-events-test-")
os.environ["AC_DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/events.db"

from sqlalchemy import select  # noqa: E402

from app import events, notify  # noqa: E402
from app.config import SESSION_COOKIE  # noqa: E402
from app.routers import live  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import User  # noqa: E402

PASSED = 0


def check(label: str, condition: bool) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"✗ {label}")
    PASSED += 1
    print(f"  ✓ {label}")


def run(coro):
    return asyncio.run(coro)


def make_user(db, handle: str) -> User:
    user = User(handle=handle, display_name=handle.upper())
    db.add(user)
    db.commit()
    return user


def find_user(db, handle: str) -> User:
    return db.scalar(select(User).where(User.handle == handle))


# ---------------- 訊息框格式 ----------------


def suite_frame() -> None:
    print("[1] SSE 訊息框格式")
    frame = live._frame("notification", {"type": "notification", "preview": "切磋會有人回應"})
    check("以 event 行開頭", frame.startswith("event: notification\n"))
    check("data 行為單行 JSON 且以空行收尾", frame.count("\n") == 3 and frame.endswith("\n\n"))
    body = frame.split("data: ", 1)[1].strip()
    check("payload 可被解析回原物件", json.loads(body)["preview"] == "切磋會有人回應")
    check("中文不轉成 \\u 逃脫碼", "切磋會" in body)
    check("內含換行的值仍維持單行 data", json.dumps({"a": "x\ny"}) .count("\n") == 0)


# ---------------- 訂閱清單 ----------------


def suite_subscribers() -> None:
    print("[2] 訂閱與名單")
    check("未訂閱時該使用者為 0 條", events.subscriber_count(12345) == 0)

    base = events.subscriber_count()
    q1 = events.subscribe(11111)
    q2 = events.subscribe(11111)
    q3 = events.subscribe(22222)
    check("同一人多條連線（多分頁）都算", events.subscriber_count(11111) == 2)
    check("全域計數包含所有人", events.subscriber_count() == base + 3)

    check("沒有事件圈時投遞為 0 且不炸", events.publish(11111, {"type": "x"}) == 0)

    events.unsubscribe(11111, q1)
    events.unsubscribe(11111, q2)
    check("退訂後清單不再保留該人", events.subscriber_count(11111) == 0)

    events.unsubscribe(11111, q1)  # 重複退訂不該炸
    check("重複退訂無害", events.subscriber_count(11111) == 0)

    events.unsubscribe(22222, q3)
    check("全部退訂後回到基準", events.subscriber_count() == base)


# ---------------- 投遞與交易掛勾 ----------------


def suite_publish() -> None:
    print("[3] 投遞與交易掛勾")
    init_db()
    events.install()
    db = SessionLocal()
    try:
        alice = make_user(db, "e-alice")
        bob = make_user(db, "e-bob")

        async def scenario() -> None:
            events.bind_loop(asyncio.get_running_loop())
            qa = events.subscribe(alice.id)
            qb = events.subscribe(bob.id)

            # 未 commit 前只暫存在 Session 裡，不該先送出去
            events.queue_event(db, alice.id, {"type": "notification", "preview": "先別送"})
            await asyncio.sleep(0.05)
            check("commit 前不投遞", qa.qsize() == 0)

            db.commit()
            await asyncio.sleep(0.05)
            check("commit 後投遞", qa.qsize() == 1)
            check("別人的佇列不受影響", qb.qsize() == 0)
            check("投遞內容與排入的一致", (await qa.get())["preview"] == "先別送")

            # rollback：真的動過資料再回滾，事件要一起被丟掉
            # （要 flush 出一次真交易，SQLAlchemy 才會發 after_rollback）
            note = notify.push(
                db,
                recipient_id=alice.id,
                actor_id=bob.id,
                kind="like",
                preview="不該出現",
            )
            db.flush()
            check("先寫進交易裡的一則通知", note is not None)
            db.rollback()
            await asyncio.sleep(0.05)
            check("rollback 後不投遞", qa.qsize() == 0)

            db.commit()
            await asyncio.sleep(0.05)
            check("rollback 的事件不會殘留到下次 commit", qa.qsize() == 0)

            # 佇列滿了就丟掉最新一則，不能拖慢或炸掉交易
            for i in range(events.QUEUE_SIZE + 5):
                events.queue_event(db, alice.id, {"type": "notification", "seq": i})
            db.commit()
            await asyncio.sleep(0.05)
            check("佇列滿時不超過上限", qa.qsize() == events.QUEUE_SIZE)
            check("保留的是最早的那批", (await qa.get())["seq"] == 0)

            # install 只掛一次：掛兩次的話同一則事件會被送兩次
            pending = 3
            for i in range(pending):
                events.queue_event(db, bob.id, {"type": "notification", "seq": i})
            db.commit()
            await asyncio.sleep(0.05)
            check("重複 install 不會重複投遞", qb.qsize() == pending)

            events.unsubscribe(alice.id, qa)
            events.unsubscribe(bob.id, qb)

        run(scenario())
    finally:
        db.close()


# ---------------- notify 掛進交易 ----------------


def suite_notify() -> None:
    print("[4] 通知的規則與事件內容")
    db = SessionLocal()
    try:
        actor = find_user(db, "e-alice")
        recipient = find_user(db, "e-bob")

        check(
            "不通知自己",
            notify.push(db, recipient_id=actor.id, actor_id=actor.id, kind="like") is None,
        )
        check(
            "沒有收件人就不寫",
            notify.push(db, recipient_id=None, actor_id=actor.id, kind="like") is None,
        )
        db.rollback()

        note = notify.push(
            db,
            recipient_id=recipient.id,
            actor_id=actor.id,
            kind="like",
            post_id=None,
            preview="順手點個讚",
        )
        check("寫入通知", note is not None)
        check("暫存的事件還沒送出去", bool(db.info.get("ac_pending_events")))

        # Session 是 autoflush=False，先 flush 才等同於「前一則已經落到庫裡」
        # （真實情境是一前一後兩個請求，各自 commit）
        db.flush()

        again = notify.push(
            db,
            recipient_id=recipient.id,
            actor_id=actor.id,
            kind="like",
            post_id=None,
            preview="順手點個讚",
        )
        check("同人同篇同動作只留一則", again is None)

        follow = notify.push(
            db,
            recipient_id=recipient.id,
            actor_id=actor.id,
            kind="follow",
            preview="開始追蹤你",
        )
        check("不同動作仍會通知", follow is not None)

        long_text = "第一行\n第二行" + "字" * 200
        clipped = notify.push(
            db,
            recipient_id=recipient.id,
            actor_id=actor.id,
            kind="reply",
            preview=long_text,
        )
        check("摘要壓成單行", "\n" not in clipped.preview)
        check("摘要截斷並加省略號", clipped.preview.endswith("…") and len(clipped.preview) == 81)

        payload = notify._event(db, note, "like", actor.id)
        check("事件型別固定", payload["type"] == "notification")
        check("事件帶動作人 handle", payload["actor"]["handle"] == "e-alice")

        db.commit()
        check("commit 後暫存事件已清空", not db.info.get("ac_pending_events"))

        # commit 之後才真的投遞，內容就是剛剛寫的那則
        async def scenario() -> None:
            events.bind_loop(asyncio.get_running_loop())
            queue = events.subscribe(recipient.id)
            note2 = notify.push(
                db,
                recipient_id=recipient.id,
                actor_id=actor.id,
                kind="save",
                preview="收藏了你的主題",
            )
            db.commit()
            await asyncio.sleep(0.05)
            payload2 = await queue.get()
            check("commit 後才投遞，且內容對得上", payload2["preview"] == note2.preview)
            check("事件種類沿用通知類型", payload2["kind"] == "save")
            events.unsubscribe(recipient.id, queue)

        run(scenario())

        check("未讀數等於寫入的通知數", notify.unread_count(db, recipient.id) == 4)
    finally:
        db.close()


# ---------------- 長連線的登入解析 ----------------


class _FakeRequest:
    def __init__(self, cookies: Optional[dict] = None) -> None:
        self.cookies = cookies or {}


def suite_viewer_resolution() -> None:
    print("[5] 長連線的登入解析")
    check("沒有 Cookie 也沒有 token 時解析為 None", live._resolve_viewer(_FakeRequest(), None) is None)
    check(
        "無效 token 解析為 None",
        live._resolve_viewer(_FakeRequest({SESSION_COOKIE: "not-a-real-token"}), "also-bad") is None,
    )


def main() -> int:
    suite_frame()
    suite_subscribers()
    suite_publish()
    suite_notify()
    suite_viewer_resolution()
    print(f"\n全部通過：{PASSED} 項")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
