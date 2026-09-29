"""Alembic 遷移環境。

連線字串刻意不寫在 alembic.ini，而是沿用應用程式自己的設定（`app.config`），
這樣 `alembic upgrade head` 與服務啟動看到的永遠是同一個資料庫。
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 直接在 backend/ 底下跑 `alembic` 時，把 backend/ 加進匯入路徑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: E402,F401  匯入以註冊所有資料表
from app.config import DATABASE_URL  # noqa: E402
from app.db import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# configparser 會把 % 當成插值符號，連線字串含 % 時要先轉義
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """略過 Alembic 自己的版本表，別把它當成「多出來的表」而想刪掉。"""
    if type_ == "table" and name == "alembic_version":
        return False
    return True


def run_migrations_offline() -> None:
    """離線模式：只產生 SQL，不需要連上資料庫。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite 不支援 ALTER COLUMN / DROP COLUMN，交給批次模式重建表
            render_as_batch=connection.dialect.name == "sqlite",
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
