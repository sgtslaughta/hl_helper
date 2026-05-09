"""Tests for /v1/events/sse Server-Sent Events endpoint."""

from __future__ import annotations

import asyncio
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.db.session import make_engine, make_sessionmaker
from server.app.events.bus import Bus
from server.app.models import Base
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")
    monkeypatch.setenv("FLEET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FLEET_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")


@pytest.fixture
def mock_settings():
    return FleetSettings(admin_token=SecretStr("test-tok"))


def _build_app_sync(tmp_path, db_name: str):
    app = create_app()
    db_url = f"sqlite+aiosqlite:///{tmp_path}/{db_name}.db"
    engine = make_engine(db_url)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    sm = make_sessionmaker(engine)
    bus = Bus()
    app.state.app_state = make_test_app_state(sessionmaker=sm, bus=bus)
    app.state.bus = bus
    return app, bus


async def _build_app_async(tmp_path, db_name: str):
    app = create_app()
    db_url = f"sqlite+aiosqlite:///{tmp_path}/{db_name}.db"
    engine = make_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)
    bus = Bus()
    app.state.app_state = make_test_app_state(sessionmaker=sm, bus=bus)
    app.state.bus = bus
    return app, bus


def test_sse_unauthorized_returns_401(mock_settings, tmp_path):
    app, _ = _build_app_sync(tmp_path, "sse_unauth")
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            r = client.get("/v1/events/sse?channels=ticker")
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_sse_authorized_format_helper(mock_settings, tmp_path):
    """SSE frame encoder produces valid event-stream bytes."""
    from server.app.api.v1.events_ws import _sse_format

    payload = json.dumps({"k": "v", "n": 1})
    out = _sse_format(payload)
    assert out.endswith(b"\n\n")
    assert b"data: " in out

    # No newlines in single-line JSON → single data line
    text = out.decode()
    data_lines = [ln for ln in text.split("\n") if ln.startswith("data:")]
    assert len(data_lines) == 1
    assert json.loads(data_lines[0][len("data:"):].strip()) == {"k": "v", "n": 1}


def test_sse_rejects_invalid_channel(mock_settings, tmp_path):
    app, _ = _build_app_sync(tmp_path, "sse_badch")
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            r = client.get(
                "/v1/events/sse?channels=evil",
                headers={"Authorization": "Bearer test-tok"},
            )
            assert r.status_code == 400
