from __future__ import annotations

from functools import lru_cache
import os

from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, Session, create_engine

from acgn_assistant.core.config import get_settings
from acgn_assistant.db_migrations import apply_sqlite_migrations


def _connect_args(database_url: str) -> dict:
    # SQLite 在多线程下需要该参数
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache
def _engine_for_url(database_url: str):
    # NOTE: For SQLite, avoid QueuePool (default) because under bursty/concurrent requests
    # it can exhaust pool slots and cause 500s (TimeoutError). NullPool opens/closes
    # per-checkout connections, which is safer for our lightweight SQLite usage.
    engine_kwargs = {
        "echo": False,
        "connect_args": _connect_args(database_url),
        "pool_pre_ping": True,
    }
    # Serverless (e.g. Vercel): avoid keeping DB connections around between invocations.
    # This reduces the risk of exhausting Neon/free-tier connection limits.
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        engine_kwargs["poolclass"] = NullPool
    elif database_url.startswith("sqlite"):
        engine_kwargs["poolclass"] = NullPool

    engine = create_engine(database_url, **engine_kwargs)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine():
    settings = get_settings()
    return _engine_for_url(settings.database_url)


def init_db() -> None:
    # 重要：确保所有表模型已 import，使其注册到 SQLModel.metadata
    import acgn_assistant.models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)

    # 轻量迁移：为已有 SQLite 数据库补齐新字段/索引（create_all 不会改旧表）
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        apply_sqlite_migrations(engine)


def get_session():
    with Session(get_engine()) as session:
        yield session
