"""登入態（sessions）與停權（suspension）的單元測試。

這兩個機制都只在「已經登入」的狀態下才看得到效果，壞掉時的表现是安靜的：
停權帳號還能發文、改完密碼其他裝置還進得來。所以規則用這裡釘住。

執行：
    cd backend && .venv/bin/python tests/test_sessions.py
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
_TMP_DIR = tempfile.mkdtemp(prefix="ac-sessions-test-")
os.environ["AC_DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/sessions.db"

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import deps  # noqa: E402
from app.config import SESSION_COOKIE  # noqa: E402
from app.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.models import Session, User  # noqa: E402
from app.routers.me import _drop_other_sessions  # noqa: E402
from app.security import (  # noqa: E402
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)

PASSED = 0


def check(label: str, condition: bool) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"✗ {label}")
    PASSED += 1
    print(f"  ✓ {label}")


class FakeRequest:
    """依賴只讀 request.cookies，測試不需要整個 Starlette Request。"""

    def __init__(self, token: str | None = None) -> None:
        self.cookies = {SESSION_COOKIE: token} if token else {}


def make_user(db, handle: str, *, kind: str = "human", password: str | None = None) -> User:
    user = User(handle=handle, display_name=handle.upper(), kind=kind, password_hash=password)
    db.add(user)
    db.commit()
    return user


def make_session(db, user: User, token: str, *, days: int = 30) -> Session:
    row = Session(
        token_hash=hash_token(token),
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=days),
    )
    db.add(row)
    db.commit()
    return row


# ---------------- 密碼與 token ----------------


def suite_security() -> None:
    print("[1] 密碼雜湊與 token 指紋")

    stored = hash_password("切磋會-密碼-1234")
    check("雜湊格式帶演算法與迭代次數", stored.startswith("pbkdf2_sha256$210000$"))
    check("正確密碼可驗證", verify_password("切磋會-密碼-1234", stored))
    check("錯誤密碼不通過", not verify_password("切磋會-密碼-1234 ", stored))
    check("每次加鹽，同一組密碼的雜湊不同", hash_password("same") != hash_password("same"))
    check("沒有密碼（管理員代開）一律不通過", not verify_password("anything", None))
    check("雜湊字串壞掉時不炸", not verify_password("x", "not$a$valid$hash"))
    check("演算法不符時不通過", not verify_password("x", stored.replace("pbkdf2_sha256", "md5")))

    token_a = new_session_token()
    token_b = new_session_token()
    check("token 夠長且每次不同", len(token_a) >= 32 and token_a != token_b)
    check("token 指紋為 64 位 hex 且可重現", len(hash_token(token_a)) == 64 and hash_token(token_a) == hash_token(token_a))
    check("不同 token 的指紋不同", hash_token(token_a) != hash_token(token_b))
    check("指紋不含原文", token_a not in hash_token(token_a))


# ---------------- 登入態撤銷 ----------------


def suite_drop_sessions() -> None:
    print("[2] 登入態的保留與撤銷")
    db = SessionLocal()
    try:
        alice = make_user(db, "s-alice")
        bob = make_user(db, "s-bob")
        keep = "keep-token"
        make_session(db, alice, keep)
        make_session(db, alice, "other-1")
        make_session(db, alice, "other-2")
        make_session(db, bob, "bob-token")

        removed = _drop_other_sessions(db, alice, keep)
        db.commit()
        check("只踢掉其他裝置（留下當前這條）", removed == 2)
        remain = db.scalars(select(Session).where(Session.user_id == alice.id)).all()
        check("當前這條還在", [r.token_hash for r in remain] == [hash_token(keep)])
        check("別人的登入態不受影響", len(db.scalars(select(Session).where(Session.user_id == bob.id)).all()) == 1)

        make_session(db, alice, "yet-another")
        check("沒有當前 token 時全部撤銷（例如代管端點）", _drop_other_sessions(db, alice, None) == 2)
        db.commit()
        check("撤銷後一條不剩", db.scalars(select(Session).where(Session.user_id == alice.id)).all() == [])

        check("本來就沒登入態時回傳 0", _drop_other_sessions(db, bob, "not-bob-token") == 1)
        db.commit()
    finally:
        db.close()


# ---------------- 長連線登入解析 ----------------


def suite_user_from_token() -> None:
    print("[3] SSE 長連線的登入解析")
    db = SessionLocal()
    try:
        user = make_user(db, "s-viewer")
        token = new_session_token()
        make_session(db, user, token)
        expired = new_session_token()
        make_session(db, user, expired, days=-1)
        suspended = make_user(db, "s-suspended")
        suspended.suspended_at = utcnow()
        suspended.suspended_reason = "洗版"
        db.commit()
        suspended_token = new_session_token()
        make_session(db, suspended, suspended_token)

        viewer = deps.user_from_token(token)
        check("有效 token 解析出登入者", viewer is not None and viewer.id == user.id)
        check("只帶 id 與 handle（不背 ORM 物件）", viewer.handle == "s-viewer")
        check("沒有 token 解析為 None", deps.user_from_token(None) is None)
        check("空字串解析為 None", deps.user_from_token("") is None)
        check("查不到的 token 解析為 None", deps.user_from_token("ghost-token") is None)
        check("過期的 token 解析為 None", deps.user_from_token(expired) is None)
        check("停權帳號的 token 解析為 None（長連線也進不來）", deps.user_from_token(suspended_token) is None)
    finally:
        db.close()


# ---------------- 停權與依賴 ----------------


def suite_suspension_deps() -> None:
    print("[4] 停權帳號在依賴層就被擋下")
    db = SessionLocal()
    try:
        normal = make_user(db, "s-normal")
        normal_token = new_session_token()
        make_session(db, normal, normal_token)

        banned = make_user(db, "s-banned")
        banned.suspended_at = utcnow()
        banned.suspended_reason = "廣告"
        db.commit()
        banned_token = new_session_token()
        make_session(db, banned, banned_token)

        check("一般帳號：公開頁面看得到登入者", deps.optional_user(FakeRequest(normal_token), db).id == normal.id)
        check("一般帳號：需要登入的端點放行", deps.current_user(FakeRequest(normal_token), db).id == normal.id)
        check("未登入：公開頁面解析為 None", deps.optional_user(FakeRequest(), db) is None)

        check("停權帳號：公開頁面視為未登入", deps.optional_user(FakeRequest(banned_token), db) is None)
        try:
            deps.current_user(FakeRequest(banned_token), db)
            raise AssertionError("✗ 停權帳號不該通過需要登入的端點")
        except HTTPException as exc:
            check("停權帳號：需要登入的端點擋下並回 403", exc.status_code == 403)
            check("附帶可讀的原因", "停權" in exc.detail)

        check("停權欄位為空時不影響判斷", not normal.is_suspended and banned.is_suspended)

        expired_token = new_session_token()
        make_session(db, normal, expired_token, days=-1)
        check("過期的登入態視為未登入", deps.optional_user(FakeRequest(expired_token), db) is None)
        left = db.scalars(
            select(Session).where(Session.token_hash == hash_token(expired_token))
        ).all()
        check("過期的登入態順手被清掉", left == [])
    finally:
        db.close()


def main() -> int:
    init_db()
    suite_security()
    suite_drop_sessions()
    suite_user_from_token()
    suite_suspension_deps()
    print(f"\n全部通過：{PASSED} 項")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
