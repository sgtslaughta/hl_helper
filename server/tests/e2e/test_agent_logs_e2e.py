"""E2E tests for agent log ingestion and retention (Task 3.9)."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from unittest import mock

from server.app.api.app import create_app
from server.app.logs.ingest import ingest_batch
from server.app.logs.models import AgentLog
from server.app.logs.retention import LocalSink, archive_once
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


class FakeBroker:
    """Fake event broker for testing."""

    def __init__(self) -> None:
        """Initialize broker."""
        self.calls: list[dict] = []

    def publish(self, *args, **kw) -> None:
        """Record published events."""
        if kw:
            self.calls.append(kw)
        elif args:
            self.calls.append({"event": args[0]})


def _entry(seq: int, ts: datetime) -> dict:
    """Create a test log entry."""
    doc = {
        "@timestamp": ts.isoformat(),
        "ecs.version": "8.11",
        "event": {
            "kind": "event",
            "category": ["task"],
            "action": "task.exec.completed",
            "outcome": "success",
            "sequence": seq,
            "id": f"id-{seq}",
        },
        "agent": {
            "id": "a",
            "type": "hl-agent",
            "session_id": "s",
            "version": "0.4.1",
        },
        "host": {"id": "h1", "name": "edge-07"},
        "log": {"level": "info", "logger": "agent.task"},
        "labels": {},
        "details": {"rc": 0},
    }
    return {
        "seq": seq,
        "ts": doc["@timestamp"],
        "level": "info",
        "action": "task.exec.completed",
        "category": "task",
        "outcome": "success",
        "payload": gzip.compress(json.dumps(doc).encode()),
    }


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    """Set admin token in environment."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")


@pytest.fixture
def auth():
    """Return admin auth headers."""
    return {"Authorization": "Bearer test-tok"}


@pytest.fixture
def mock_settings():
    """Return mocked settings with admin token."""
    return FleetSettings(admin_token=SecretStr("test-tok"))


@pytest.fixture
async def client(sm, auth, mock_settings):
    """Create FastAPI test client with admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            yield c


@pytest.mark.asyncio
async def test_e2e_ingest_list_archive(sm, db_session, tmp_path) -> None:
    """E2E test: ingest logs, list them, age some, archive, verify state."""
    now = datetime.now(timezone.utc)
    entries = [_entry(1, now), _entry(2, now), _entry(3, now)]

    # Ingest logs using sync session
    broker = FakeBroker()
    ingest_batch(
        db_session,
        broker,
        host_id="h1",
        agent_id="a",
        agent_session_id="s",
        agent_version="0.4.1",
        entries=entries,
        dictionary=None,
    )

    # Verify rows inserted
    rows = db_session.execute(select(AgentLog)).scalars().all()
    assert len(rows) == 3

    # Age 2 rows to > 30 days
    db_session.execute(
        update(AgentLog)
        .where(AgentLog.seq <= 2)
        .values(ts=now - timedelta(days=40))
    )
    db_session.commit()

    # Archive with 30-day threshold
    sink = LocalSink(tmp_path / "arc")
    result = archive_once(db_session, sink, hot_days=30, now=now)
    assert result["archived_rows"] == 2
    assert result["files_written"] == 1

    # Verify hot table now has 1 row
    remaining = db_session.execute(select(AgentLog)).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].seq == 3

    # Verify archive files exist
    archive_files = sink.list_keys("agent_logs/")
    assert len(archive_files) == 1


@pytest.mark.asyncio
async def test_e2e_rest_list_endpoint(sm, auth, mock_settings) -> None:
    """E2E test: ingest logs and verify REST endpoint returns them."""
    from sqlalchemy import insert as sql_insert

    # Set up app and client
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    now = datetime.now(timezone.utc)
    entries = [_entry(1, now), _entry(2, now), _entry(3, now)]

    # Insert logs using async session (same DB as the client will use)
    async with sm() as session:
        logs_data = []
        for i, entry in enumerate(entries, 1):
            doc = json.loads(gzip.decompress(entry["payload"]))
            logs_data.append({
                "id": i,
                "host_id": "h1",
                "agent_id": "a",
                "agent_session_id": "s",
                "agent_version": "0.4.1",
                "seq": entry["seq"],
                "ts": datetime.fromisoformat(entry["ts"]),
                "level": 20,
                "action": "task.exec.completed",
                "category": "task",
                "outcome": 1,
                "message": None,
                "labels": {},
                "details": {},
            })

        await session.execute(sql_insert(AgentLog), logs_data)
        await session.commit()

    # Query REST API
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs?host_id=h1", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_e2e_purge_archive(db_session, tmp_path) -> None:
    """E2E test: archive logs, then purge with retention=0 days."""
    from server.app.logs.retention import purge_archive
    import os
    import time

    now = datetime.now(timezone.utc)
    entries = [_entry(1, now), _entry(2, now)]

    # Insert logs using sync session
    broker = FakeBroker()
    ingest_batch(
        db_session,
        broker,
        host_id="h1",
        agent_id="a",
        agent_session_id="s",
        agent_version="0.4.1",
        entries=entries,
        dictionary=None,
    )

    # Age all rows
    db_session.execute(
        update(AgentLog)
        .where(AgentLog.seq >= 0)
        .values(ts=now - timedelta(days=40))
    )
    db_session.commit()

    # Archive
    sink = LocalSink(tmp_path / "arc")
    archive_once(db_session, sink, hot_days=30, now=now)

    # Verify files exist
    files_before = sink.list_keys("agent_logs/")
    assert len(files_before) > 0

    # Age the archive files to > 0 days old by setting their mtime to 2 days ago
    archive_cutoff = now - timedelta(days=2)
    archive_cutoff_ts = archive_cutoff.timestamp()
    for key in files_before:
        filepath = tmp_path / "arc" / key
        os.utime(filepath, (archive_cutoff_ts, archive_cutoff_ts))

    # Purge with retention_days=0 (delete anything older than "now")
    deleted = purge_archive(sink, retention_days=0, now=now)
    assert deleted > 0

    # Verify files deleted
    files_after = sink.list_keys("agent_logs/")
    assert len(files_after) == 0
