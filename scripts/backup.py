#!/usr/bin/env python3
"""SQLite 線上熱備份。

WAL 模式下直接 cp 檔案會拿到「主庫已更新、WAL 還沒併入」的不完整狀態，
必須走 sqlite3 的 backup API 才安全；本腳本同時做 integrity_check 並保留最近數份。

用法：
    backend/.venv/bin/python scripts/backup.py [保留份數，預設 14]
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def load_env(path: Path) -> None:
    """讀取 KEY=VALUE 形式的 .env（不覆蓋既有環境變數）。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    keep = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    load_env(BACKEND / ".env")
    sys.path.insert(0, str(BACKEND))
    from app.config import DATABASE_URL  # noqa: PLC0415  需先備妥 sys.path 與環境變數

    if not DATABASE_URL.startswith("sqlite"):
        print("偵測到非 SQLite 資料庫（%s），請改用 pg_dump 備份。" % DATABASE_URL.split("@")[-1])
        return 1

    db_path = Path(DATABASE_URL.split("sqlite:///", 1)[1])
    if not db_path.is_absolute():
        db_path = (BACKEND / db_path).resolve()
    if not db_path.exists():
        print("找不到資料庫檔案：%s" % db_path)
        return 1

    backup_dir = BACKEND / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"community-{stamp}.db"

    with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)

    with sqlite3.connect(str(target)) as conn:
        status = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]

    if status != "ok":
        print("備份檔完整性檢查失敗：%s" % status)
        return 1

    size_kb = target.stat().st_size / 1024
    print(f"備份完成：{target}（{size_kb:.1f} KB，{tables} 張表，integrity_check=ok）")

    old = sorted(backup_dir.glob("community-*.db"))[:-keep] if keep > 0 else []
    for stale in old:
        stale.unlink()
    if old:
        print(f"已清除 {len(old)} 份過期備份，保留最近 {keep} 份。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
