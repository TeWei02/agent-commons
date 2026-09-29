#!/usr/bin/env python3
"""把某個帳號設為站務（或解除）。

站務權限刻意不開放線上自助提權 —— 那是權限提升漏洞的經典入口。
第一個站務只能從主機上這樣指定：

    python3 scripts/grant_admin.py viewer@example.com
    python3 scripts/grant_admin.py viewer@example.com --revoke

之後就可以用站務帳號在 /api/admin 介面裡處理後續的人員調整。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal, ensure_schema  # noqa: E402
from app.models import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="指派或解除站務權限")
    parser.add_argument("identifier", help="帳號的 Email 或 handle（例如 u-0007）")
    parser.add_argument("--revoke", action="store_true", help="改為解除站務權限")
    args = parser.parse_args()

    ensure_schema()
    target = args.identifier.strip().lower()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == target).one_or_none()
        if user is None:
            user = db.query(User).filter(User.handle == target).one_or_none()
        if user is None:
            print(f"找不到帳號：{args.identifier}", file=sys.stderr)
            return 1

        user.is_admin = not args.revoke
        db.commit()

        state = "已解除站務" if args.revoke else "已設為站務"
        print(f"{state}：{user.display_name} (@{user.handle}, {user.email or '無 Email'})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
