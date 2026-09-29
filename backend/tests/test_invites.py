"""邀請碼模組的單元測試。

不需要起服務：直接對 app.invites 的狀態機下斷言。這是註冊核銷、後台管理
與 CLI 三個入口共用的那份邏輯，規則一旦漂移會先在這裡炸出來。

執行：
    cd backend && .venv/bin/python tests/test_invites.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 用臨時資料庫，不碰開發庫；必須在 import app.db 之前設好
_TMP_DIR = tempfile.mkdtemp(prefix="ac-invites-test-")
os.environ["AC_DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/invites.db"

from app import invites  # noqa: E402
from app.db import SessionLocal, init_db, utcnow  # noqa: E402

PASSED = 0


def check(label: str, condition: bool) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"✗ {label}")
    PASSED += 1
    print(f"  ✓ {label}")


def expect_error(label: str, fn, needle: str) -> None:
    """期望丟 InviteError，且訊息含關鍵字——這些訊息會直接顯示給註冊者看。"""
    try:
        fn()
    except invites.InviteError as exc:
        check(f"{label}（{exc}）", needle in str(exc))
        return
    raise AssertionError(f"✗ {label} — 應該被擋下卻通過了")


def suite_format() -> None:
    print("[1] 碼的格式")
    check("去連字號、空白與大小寫：ab-cd ef → ABCDEF", invites.normalize("ab-cd ef") == "ABCDEF")
    check("顯示格式每 4 碼分一組", invites.format_code("ABCDEFGH") == "ABCD-EFGH")
    check("產生長度符合要求", len(invites.new_code(10)) == 10)
    check("長度下限鎖在 6", len(invites.new_code(2)) == 6)
    banned = set("IO01")
    check("整批新碼不含易混淆字元", all(not (set(invites.new_code(8)) & banned) for _ in range(200)))


def suite_lifecycle(db) -> None:
    print("[2] 生命週期與核銷")
    inv = invites.create(db, note="單元測試", max_uses=2, days=7)
    check("新碼為啟用中", invites.status_of(inv) == invites.ACTIVE)
    check("剩餘次數等於上限", invites.remaining_uses(inv) == 2)
    check("用顯示格式（帶連字號）也找得到", invites.find(db, invites.format_code(inv.code)).id == inv.id)
    check("小寫也找得到", invites.find(db, inv.code.lower()).id == inv.id)

    invites.redeem(db, inv.code)
    db.commit()
    check("核銷一次後剩 1", invites.remaining_uses(inv) == 1)
    invites.redeem(db, inv.code)
    db.commit()
    check("用盡後狀態轉為 used_up", invites.status_of(inv) == invites.USED_UP)
    check("用盡後不列在 active", inv.id not in [r.id for r in invites.list_all(db, status=invites.ACTIVE)])
    check("用盡後列在 used_up", inv.id in [r.id for r in invites.list_all(db, status=invites.USED_UP)])
    expect_error("額度用盡後再核銷被擋", lambda: invites.redeem(db, inv.code), "已用完")
    check("失敗的核銷不會偷扣次數", inv.used_count == 2)

    expect_error("空碼被擋", lambda: invites.redeem(db, "  -  "), "需要邀請碼")
    expect_error("不存在的碼被擋", lambda: invites.redeem(db, "ZZZZZZZZ"), "不正確")
    expect_error("長度不足的自訂碼被擋", lambda: invites.create(db, code="abc"), "英數")
    expect_error("含非英數的自訂碼被擋", lambda: invites.create(db, code="邀請碼"), "英數")

    dup = invites.create(db, code="abc-defgh", max_uses=1)
    check("自訂碼正規化後存入", dup.code == "ABCDEFGH")
    expect_error("撞號被擋", lambda: invites.create(db, code="abcdefgh"), "已經存在")

    gone = invites.create(db, max_uses=1)
    invites.revoke(db, gone)
    check("撤銷後狀態為 revoked", invites.status_of(gone) == invites.REVOKED)
    expect_error("撤銷後核銷被擋", lambda: invites.redeem(db, gone.code), "撤銷")
    check("撤銷後不列在 active", gone.id not in [r.id for r in invites.list_all(db, status=invites.ACTIVE)])

    stale = invites.create(db, max_uses=1, days=1)
    stale.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    check("過期狀態判定", invites.status_of(stale) == invites.EXPIRED)
    expect_error("過期後核銷被擋", lambda: invites.redeem(db, stale.code), "過期")
    check("過期碼列在 expired", stale.id in [r.id for r in invites.list_all(db, status=invites.EXPIRED)])
    check("撤銷優先於過期", invites.status_of(invites.revoke(db, stale)) == invites.REVOKED)


def suite_limit(db) -> None:
    print("[3] 列表與上限")
    for _ in range(3):
        invites.create(db, max_uses=1)
    rows = invites.list_all(db, limit=2)
    check("limit 生效", len(rows) == 2)
    check("新的排前面", rows[0].id > rows[1].id)
    check("未知狀態不過濾", len(invites.list_all(db, status="whatever", limit=200)) >= 3)


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        suite_format()
        suite_lifecycle(db)
        suite_limit(db)
    finally:
        db.close()
    print(f"\n全部通過：{PASSED} 項")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
