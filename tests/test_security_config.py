"""Regression tests for the security/configuration fixes.

These guard two problems that were live in the application layer:

  * CORS was configured as ``allow_origins=["*"]`` together with
    ``allow_credentials=True`` — browsers reject that combination, and where
    it is honoured any website can issue credentialed cross-origin requests
    against the API.
  * The schema was only ever built by ``Base.metadata.create_all``, which
    creates missing tables but never adds a column to an existing one, so a
    deployed database silently stopped tracking the models. Schema changes
    now go through Alembic.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.config import Settings

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

def test_cors_origins_parsed_from_csv() -> None:
    settings = Settings(CORS_ORIGINS="https://frigocore.pl, http://localhost:5173")
    assert settings.cors_origins == ["https://frigocore.pl", "http://localhost:5173"]


def test_cors_wildcard_is_never_allowed() -> None:
    """A wildcard must not survive into the allowlist.

    ``allow_credentials=True`` is on, so a "*" entry would be exactly the
    misconfiguration this fix removes.
    """
    settings = Settings(CORS_ORIGINS="*")
    assert settings.cors_origins == []

    mixed = Settings(CORS_ORIGINS="*,https://frigocore.pl")
    assert mixed.cors_origins == ["https://frigocore.pl"]


def test_cors_blank_entries_are_dropped() -> None:
    assert Settings(CORS_ORIGINS="").cors_origins == []
    assert Settings(CORS_ORIGINS=" , ,").cors_origins == []


def test_app_is_not_mounted_with_wildcard_cors() -> None:
    """The running app must never carry a wildcard origin allowlist."""
    from fastapi.middleware.cors import CORSMiddleware  # noqa: PLC0415

    from app.main import app  # noqa: PLC0415

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS middleware is not installed"
    for middleware in cors:
        assert "*" not in middleware.kwargs["allow_origins"]


# ---------------------------------------------------------------------------
# Alembic migrations
# ---------------------------------------------------------------------------

def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return cfg


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch):
    """Run `alembic upgrade head` against an empty SQLite file."""
    db_path = tmp_path / f"{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    command.upgrade(_alembic_config(db_path), "head")
    return db_path


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_migrations_build_the_full_schema(migrated_db) -> None:
    assert {
        "objects",
        "sensors",
        "users",
        "alarms",
        "alarm_configs",
        "measurements",
        "notification_profiles",
        "notification_endpoints",
        "alembic_version",
    } <= _tables(migrated_db)


def test_migrations_match_the_models(migrated_db) -> None:
    """Every mapped column must exist in the migrated schema.

    This is what catches a model field added without a migration — the exact
    failure mode create_all hid.
    """
    from app.models.base import Base  # noqa: PLC0415

    for table in Base.metadata.sorted_tables:
        missing = {c.name for c in table.columns} - _columns(migrated_db, table.name)
        assert not missing, f"{table.name} is missing migrated column(s): {sorted(missing)}"


BASELINE_REVISION = "0f603005f247"


def test_baseline_adopts_a_pre_alembic_database(tmp_path) -> None:
    """A database created by the old create_all path must upgrade cleanly.

    Deployed installations predate Alembic: they hold the pre-Alembic schema
    plus real data and have no alembic_version table. The baseline revision
    has to adopt them in place — not try to re-create their tables — and
    later revisions must then apply on top without losing rows.
    """
    db_path = tmp_path / "legacy.db"
    cfg = _alembic_config(db_path)

    # Build the schema as it was before Alembic existed, then strip the
    # version table so the database looks unmanaged, exactly like production.
    command.upgrade(cfg, BASELINE_REVISION)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE alembic_version")
    object_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO objects (id, name, description, is_active, created_at, updated_at)"
        " VALUES (?, 'Legacy', '', 1, '2026-01-01', '2026-01-01')",
        (object_id,),
    )
    conn.execute(
        "INSERT INTO sensors (id, name, mqtt_topic, offline_timeout_seconds, is_active,"
        " object_id, created_at, updated_at)"
        " VALUES (?, 'Legacy sensor', 'frigo/legacy/a', 120, 1, ?, '2026-01-01', '2026-01-01')",
        (uuid.uuid4().hex, object_id),
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")

    assert "alembic_version" in _tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT count(*) FROM objects").fetchone()[0] == 1
        # The new NOT NULL columns must have been backfilled on the existing
        # row rather than failing the upgrade.
        icon, order, offset = conn.execute(
            "SELECT icon, display_order, calibration_offset FROM sensors"
        ).fetchone()
        assert (icon, order, offset) == ("thermometer", 0, 0.0)
    finally:
        conn.close()
