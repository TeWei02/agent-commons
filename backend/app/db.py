"""資料庫連線與 Session。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if IS_SQLITE else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)


if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 連線層
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def utcnow() -> datetime:
    """一律使用 naive UTC，避免 SQLite / PostgreSQL 時區語意打架。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 既有資料庫需要補上的欄位。只做 ADD COLUMN —— 改型別 / 刪欄位請用 Alembic。
# 沒有這張表的話，升版後既有社群會因為缺欄位而整站 500。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "is_admin": "BOOLEAN NOT NULL DEFAULT 0",
        "invite_code": "VARCHAR(32) NOT NULL DEFAULT ''",
        "suspended_at": "DATETIME",
        "suspended_reason": "VARCHAR(200) NOT NULL DEFAULT ''",
    },
    "posts": {
        "edited_at": "DATETIME",
        "source_url": "VARCHAR(500) NOT NULL DEFAULT ''",
        "source_label": "VARCHAR(120) NOT NULL DEFAULT ''",
    },
    "replies": {
        "edited_at": "DATETIME",
    },
}


def ensure_schema() -> None:
    """為既有資料庫補上新增欄位（輕量遷移）。

    新建的資料庫由 `Base.metadata.create_all()` 一次建好，這裡只處理
    「已經有資料、之後才加的欄位」。非 SQLite 請改用 Alembic。
    """
    if not IS_SQLITE:
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    """把資料庫結構帶到最新版（Alembic 遷移）。

    三種情境：
    - **全新資料庫**：直接跑遷移，由 baseline 版本把表建好。
    - **舊版留下的資料庫**（有表、但沒有 alembic_version）：先用 metadata
      與補欄位邏輯追平結構，再一次性標記為最新版，避免遷移腳本對著
      已經存在的表重複 CREATE。
    - **已納入版控的資料庫**：套用還沒跑過的遷移。

    `alembic upgrade head` 手動執行也走同一套設定（見 migrations/env.py）。
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

    tables = set(inspect(engine).get_table_names())

    if "alembic_version" in tables:
        command.upgrade(cfg, "head")
        return

    if tables:
        Base.metadata.create_all(bind=engine)
        ensure_schema()
        command.stamp(cfg, "head")
        print("[db] 既有資料庫：補齊欄位後標記為最新版。")
        return

    command.upgrade(cfg, "head")
