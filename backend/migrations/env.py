"""Alembic migration environment for FrigoCore.

Runs against the async engine configured by `app.config.settings`, so
`alembic upgrade head` and the application always target the same database.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import *  # noqa: F401,F403 — register every model on Base.metadata
from app.models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Target database URL.

    Normally the application's own `settings.DATABASE_URL`, so migrations and
    the running app can never drift apart. An explicit `sqlalchemy.url` on the
    Alembic config wins, which is how tests and one-off manual upgrades point
    at a different database.
    """
    return config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL


def _run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot ALTER most column properties in place; batch mode
        # rewrites the table instead. Harmless on PostgreSQL.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(_database_url(), poolclass=None)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
