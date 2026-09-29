#!/usr/bin/env python3
"""邀請碼命令列工具：產生、列出、撤銷。

站務想一次發一批、或手上只有終端機時用這支。規則與後台 API 共用
`app.invites`，有效期、次數、狀態判定不會兩邊各寫一套。

    cd backend && .venv/bin/python ../scripts/invite.py new --count 5 --note "第一批"
    cd backend && .venv/bin/python ../scripts/invite.py list
    cd backend && .venv/bin/python ../scripts/invite.py revoke ABCD-EFGH
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import invites  # noqa: E402
from app.config import INVITE_REQUIRED  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

STATUS_LABEL = {
    invites.ACTIVE: "可用",
    invites.USED_UP: "已用完",
    invites.EXPIRED: "已過期",
    invites.REVOKED: "已撤銷",
}


def describe(invite) -> str:
    parts = [
        invites.format_code(invite.code),
        f"[{STATUS_LABEL[invites.status_of(invite)]}]",
        f"用量 {invite.used_count}/{invite.max_uses}",
    ]
    if invite.expires_at:
        parts.append(f"到期 {invite.expires_at:%Y-%m-%d}")
    if invite.note:
        parts.append(f"備註 {invite.note}")
    return "  ".join(parts)


def cmd_new(args: argparse.Namespace) -> int:
    if args.code and args.count != 1:
        print("--code 只能搭配 --count 1：自訂碼一次只發一組。", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        made = []
        for _ in range(args.count):
            made.append(
                invites.create(
                    db,
                    code=args.code,
                    note=args.note,
                    max_uses=args.uses,
                    days=args.days,
                    commit=False,
                )
            )
        db.commit()
        for invite in made:
            print(describe(invite))
        print(f"\n共產生 {len(made)} 組。")
        if not INVITE_REQUIRED:
            print("提醒：目前 AC_INVITE_REQUIRED 未開，註冊不強制邀請碼（這些碼先備著）。")
    finally:
        db.close()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        rows = invites.list_all(db, status=args.status, limit=args.limit)
        if not rows:
            print("沒有符合的邀請碼。")
            return 0
        for row in rows:
            print(describe(row))
        print(f"\n共 {len(rows)} 組。")
    finally:
        db.close()
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        invite = invites.find(db, args.code)
        if invite is None:
            print(f"找不到邀請碼：{args.code}", file=sys.stderr)
            return 1
        if invite.revoked_at is not None:
            print(f"這組早就撤銷過了：{describe(invite)}")
            return 0
        invites.revoke(db, invite)
        print(f"已撤銷：{describe(invite)}")
    finally:
        db.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="邀請碼管理")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="產生邀請碼")
    new.add_argument("--count", type=int, default=1, help="產生幾組（預設 1）")
    new.add_argument("--note", default="", help="備註：發給誰、什麼用途")
    new.add_argument("--uses", type=int, default=1, help="每組可用次數（預設 1）")
    new.add_argument("--days", type=int, default=None, help="幾天後過期（預設不過期）")
    new.add_argument("--code", default=None, help="自訂碼（6–32 位英數，預設隨機）")
    new.set_defaults(func=cmd_new)

    listing = sub.add_parser("list", help="列出邀請碼")
    listing.add_argument(
        "--status", default="", choices=["", "active", "used_up", "expired", "revoked"],
        help="只看某種狀態",
    )
    listing.add_argument("--limit", type=int, default=100, help="最多列幾筆（預設 100）")
    listing.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", help="撤銷邀請碼")
    revoke.add_argument("code", help="邀請碼（連字號可省略）")
    revoke.set_defaults(func=cmd_revoke)

    args = parser.parse_args()
    # 命令列的輸出要能直接貼給人：alembic 的 INFO 對「發一組碼」沒有幫助
    logging.getLogger("alembic").setLevel(logging.WARNING)
    init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
