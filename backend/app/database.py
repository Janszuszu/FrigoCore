"""FrigoCore — Async SQLAlchemy engine and session factory.

Supports both PostgreSQL (production) and SQLite (development).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.models import *  # noqa: F403 — ensure all models are registered on Base.metadata
from app.models.base import Base

if TYPE_CHECKING:
    from alembic.config import Config


# Async engine — automatically adapts to SQLite vs PostgreSQL
_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=_connect_args,
    pool_pre_ping=True if not settings.DATABASE_URL.startswith("sqlite") else False,
)

# SQLite foreign key enforcement
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """Dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _alembic_config() -> "Config":
    """Alembic config pointing at backend/migrations, wherever we run from."""
    from alembic.config import Config  # noqa: PLC0415

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "migrations"))
    return cfg


async def init_db() -> None:
    """Bring the database schema up to date via Alembic.

    This used to be `Base.metadata.create_all`, which only ever creates
    missing *tables* — a new column on an existing table was silently never
    applied, so a deployed database could not follow the models. Migrations
    run in a worker thread because Alembic's env.py drives its own event
    loop.
    """
    from alembic import command  # noqa: PLC0415

    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
