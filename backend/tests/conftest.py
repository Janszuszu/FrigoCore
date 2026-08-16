"""FrigoCore backend — pytest fixtures.

Uses a real SQLite file, migrated through Alembic exactly the way
`app.database.init_db` does in production, so the test suite also exercises
"does the migration actually work" rather than trusting a
`Base.metadata.create_all` shortcut. DATABASE_URL must be pointed at the test
file BEFORE any `app.*` module is imported, since `app.config.settings` is a
module-level singleton read once at import time.
"""

from __future__ import annotations

import os
from pathlib import Path

_TEST_DB_PATH = Path(__file__).parent / "_test_frigocore.db"
for suffix in ("", "-shm", "-wal"):
    p = Path(str(_TEST_DB_PATH) + suffix)
    if p.exists():
        p.unlink()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["ENVIRONMENT"] = "test"

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import routes as r
from app.core.security import create_access_token, hash_password
from app.database import Base, async_session_factory, engine, get_db, init_db
from app.enums import UserRole
from app.models.user import User


def build_test_app() -> FastAPI:
    """A FastAPI app wired with the real routers but no lifespan — tests
    drive the escalation engine explicitly via `run_once()` rather than
    racing a background asyncio loop, and skip MQTT/auto-seed entirely."""
    app = FastAPI()
    app.include_router(r.auth_router, prefix="/api/v1/auth")
    app.include_router(r.objects_router, prefix="/api/v1/objects")
    app.include_router(r.users_router, prefix="/api/v1/users")
    app.include_router(r.sensors_router, prefix="/api/v1/objects")
    app.include_router(r.alarm_configs_router, prefix="/api/v1/sensors")
    app.include_router(r.alarms_router, prefix="/api/v1/alarms")
    app.include_router(r.measurements_router, prefix="/api/v1/sensors")
    app.include_router(r.notifications_router, prefix="/api/v1/objects")
    app.include_router(r.devices_router, prefix="/api/v1/devices")
    app.include_router(r.escalation_policies_router, prefix="/api/v1/escalation-policies")
    return app


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _migrated_db():
    await init_db()
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Full isolation between tests without the complexity of nesting the
    app's own commits inside a rolled-back outer transaction — the app layer
    commits directly, so we just truncate everything before each test."""
    async with async_session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
    yield


@pytest_asyncio.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    app = build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def make_user(db_session):
    counter = {"n": 0}

    async def _make(role: UserRole = UserRole.USER, is_active: bool = True) -> User:
        counter["n"] += 1
        user = User(
            username=f"{role.value}_{counter['n']}",
            email=f"{role.value}_{counter['n']}@test.local",
            hashed_password=hash_password("pw12345"),
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make


def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user)}"}
