"""Fixtures for agent logs tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from server.app.models import Base


@pytest.fixture
def _sync_engine():
    """Create an in-memory SQLite engine with proper pragmas."""
    engine = create_engine("sqlite:///:memory:")

    # Set SQLite pragmas for consistency with production
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _conn_record):
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA synchronous=NORMAL")
        finally:
            cur.close()

    # Create all tables
    Base.metadata.create_all(engine)

    # For SQLite, fix BigInteger PK issue by recreating tables with INTEGER PK
    with engine.begin() as conn:
        # Check if table exists
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_logs'"
        )).scalar()

        if result:
            # Drop and recreate with INTEGER PK instead of BIGINT
            conn.execute(text("DROP TABLE IF EXISTS agent_logs"))
            conn.execute(text("""
                CREATE TABLE agent_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    agent_session_id TEXT NOT NULL,
                    agent_version TEXT,
                    seq BIGINT NOT NULL,
                    ts DATETIME NOT NULL,
                    level SMALLINT NOT NULL,
                    action TEXT NOT NULL,
                    category TEXT NOT NULL,
                    outcome SMALLINT,
                    duration_ns BIGINT,
                    message TEXT,
                    labels JSON NOT NULL DEFAULT '{}',
                    details JSON NOT NULL DEFAULT '{}',
                    error JSON,
                    ingested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (agent_session_id, seq)
                )
            """))

        # Fix agent_log_policies similarly
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_log_policies'"
        )).scalar()

        if result:
            # Drop and recreate with INTEGER PK instead of BIGINT
            conn.execute(text("DROP TABLE IF EXISTS agent_log_policies"))
            conn.execute(text("""
                CREATE TABLE agent_log_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL UNIQUE,
                    policy_json JSON NOT NULL,
                    policy_version INTEGER NOT NULL DEFAULT 1,
                    expires_at DATETIME,
                    created_by TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_sync_engine):
    """Provide a sync session for tests."""
    SessionLocal = sessionmaker(bind=_sync_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
