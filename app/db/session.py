from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger("eoms.db")


def _build_engine() -> Engine:
    url = settings.resolved_database_url
    common: dict = {"echo": settings.db_echo, "future": True, "pool_pre_ping": True}
    if settings.is_sqlite:
        common.update(
            {
                "connect_args": {"check_same_thread": False, "timeout": 30},
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
            }
        )
    else:
        common.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout,
                "pool_recycle": 1800,
                "connect_args": {
                    "connect_timeout": 5,
                    "application_name": "eoms-api",
                    "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
                },
            }
        )
    return create_engine(url, **common)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
    if settings.is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def get_db() -> Iterator[Session]:
    """请求级事务：统一提交/回滚，保证审批与业务回调的本地一致性。"""
    db = SessionLocal()
    try:
        db.begin()
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """后台任务/脚本使用的事务上下文（受信任系统上下文，RLS 放行）。"""
    db = SessionLocal()
    try:
        db.begin()
        if settings.rls_enabled and settings.is_postgres:
            from sqlalchemy import text

            db.execute(text("SELECT set_config('app.bypass', 'on', true)"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """仅开发/测试使用；生产以 Alembic 迁移为准。"""
    from app import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)
    logger.info("数据库表已初始化")
