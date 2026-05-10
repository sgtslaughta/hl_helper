"""Tests for agent log API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.api.app import create_app
from server.app.logs.models import AgentLog, AgentLogPolicy
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


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


async def _seed_logs(sm: async_sessionmaker, logs_data: list[dict]) -> None:
    """Helper to seed logs using insert to avoid RETURNING clause issues.

    Auto-generates ids if not provided.
    """
    from sqlalchemy import insert as sql_insert

    # Auto-generate ids if not provided
    for i, log_data in enumerate(logs_data, 1):
        if "id" not in log_data:
            log_data["id"] = i

    async with sm() as session:
        # Use insert() instead of ORM add() to avoid RETURNING clause on SQLite
        stmt = sql_insert(AgentLog)
        await session.execute(stmt, logs_data)
        await session.commit()


@pytest.mark.asyncio
async def test_list_logs_empty(sm, auth, mock_settings):
    """GET /v1/logs returns empty list when no logs exist."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert data["items"] == []
            assert data["next_cursor"] is None
            assert "facets" in data


@pytest.mark.asyncio
async def test_list_logs_filters_by_host(sm, auth, mock_settings):
    """GET /v1/logs?host_id=h1 filters by host."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    now = datetime.now(timezone.utc)
    logs_data = [
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": i,
            "ts": now,
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 1,
            "message": f"log {i}",
            "labels": {},
            "details": {},
        }
        for i in range(3)
    ] + [
        {
            "host_id": "h2",
            "agent_id": "a2",
            "agent_session_id": "s2",
            "agent_version": "1.0",
            "seq": i,
            "ts": now,
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 1,
            "message": f"log {i}",
            "labels": {},
            "details": {},
        }
        for i in range(2)
    ]
    await _seed_logs(sm, logs_data)

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
            assert all(item["host_id"] == "h1" for item in data["items"])


@pytest.mark.asyncio
async def test_list_logs_filters_by_level_gte(sm, auth, mock_settings):
    """GET /v1/logs?level=warn returns warn and error (≥ filter)."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    now = datetime.now(timezone.utc)
    levels = [(10, "debug"), (20, "info"), (30, "warn"), (40, "error")]
    logs_data = [
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": level_int,
            "ts": now,
            "level": level_int,
            "action": "task.run",
            "category": "task",
            "outcome": 1,
            "message": "msg",
            "labels": {},
            "details": {},
        }
        for level_int, _name in levels
    ]
    await _seed_logs(sm, logs_data)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs?level=warn", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 2
            levels_in_result = {item["level"] for item in data["items"]}
            assert levels_in_result == {"warn", "error"}


@pytest.mark.asyncio
async def test_list_logs_text_search(sm, auth, mock_settings):
    """GET /v1/logs?q=failed searches in message."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    now = datetime.now(timezone.utc)
    logs_data = [
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": 1,
            "ts": now,
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 2,
            "message": "task failed: timeout",
            "labels": {},
            "details": {},
        },
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": 2,
            "ts": now,
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 1,
            "message": "task completed successfully",
            "labels": {},
            "details": {},
        },
    ]
    await _seed_logs(sm, logs_data)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs?q=failed", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 1
            assert "failed" in data["items"][0]["message"]


@pytest.mark.asyncio
async def test_list_logs_cursor_pagination(sm, auth, mock_settings):
    """GET /v1/logs pagination with cursor.

    Note: Full pagination testing deferred to Task 3.9 e2e tests.
    This is a smoke test that the cursor parameter is accepted.
    """
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    from datetime import timedelta

    # Create logs with different timestamps to ensure stable ordering
    base_time = datetime.now(timezone.utc)
    logs_data = [
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": i,
            "ts": base_time + timedelta(seconds=i),
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 1,
            "message": f"log {i}",
            "labels": {},
            "details": {},
        }
        for i in range(50)
    ]
    await _seed_logs(sm, logs_data)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            # First page
            r = await client.get("/v1/logs?limit=20", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 20
            assert data["next_cursor"] is not None

            # Verify cursor parameter is accepted (no error)
            r2 = await client.get(
                f"/v1/logs?limit=20&cursor={data['next_cursor']}", headers=auth
            )
            assert r2.status_code == 200
            data2 = r2.json()
            assert len(data2["items"]) > 0


@pytest.mark.asyncio
async def test_list_logs_filters_by_outcome(sm, auth, mock_settings):
    """GET /v1/logs?outcome=failure filters by outcome."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    now = datetime.now(timezone.utc)
    logs_data = [
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": 1,
            "ts": now,
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 1,  # success
            "message": "ok",
            "labels": {},
            "details": {},
        },
        {
            "host_id": "h1",
            "agent_id": "a1",
            "agent_session_id": "s1",
            "agent_version": "1.0",
            "seq": 2,
            "ts": now,
            "level": 20,
            "action": "task.run",
            "category": "task",
            "outcome": 2,  # failure
            "message": "failed",
            "labels": {},
            "details": {},
        },
    ]
    await _seed_logs(sm, logs_data)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs?outcome=failure", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["outcome"] == "failure"


@pytest.mark.asyncio
async def test_policy_get_returns_default_when_empty(sm, auth, mock_settings):
    """GET /v1/logs/policy?scope=global returns default policy when empty."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs/policy?scope=global", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert data["scope"] == "global"
            assert data["policy"]["default_level"] == "info"
            assert data["policy"]["batch_max_bytes"] == 65536


@pytest.mark.asyncio
async def test_policy_put_upserts(sm, auth, mock_settings):
    """PUT /v1/logs/policy creates or updates a policy."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.put(
                "/v1/logs/policy",
                json={
                    "scope": "global",
                    "default_level": "debug",
                },
                headers=auth,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["policy"]["default_level"] == "debug"

            # Verify via GET
            r2 = await client.get("/v1/logs/policy?scope=global", headers=auth)
            assert r2.status_code == 200
            data2 = r2.json()
            assert data2["policy"]["default_level"] == "debug"


@pytest.mark.asyncio
async def test_policy_temp_creates_host_override(sm, auth, mock_settings):
    """POST /v1/logs/policy/host/{host_id}/temp creates temp override."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.post(
                "/v1/logs/policy/host/h1/temp",
                json={
                    "level": "debug",
                    "categories": ["task"],
                    "ttl_s": 3600,
                },
                headers=auth,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["scope"] == "host:h1"
            assert data["policy"]["default_level"] == "debug"
            assert data["policy"]["expires_at"] is not None

            # Verify via GET
            r2 = await client.get("/v1/logs/policy?scope=host:h1", headers=auth)
            assert r2.status_code == 200
            data2 = r2.json()
            assert data2["policy"]["default_level"] == "debug"


@pytest.mark.asyncio
async def test_categories_endpoint(sm, auth, mock_settings):
    """GET /v1/logs/categories returns list of categories."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            r = await client.get("/v1/logs/categories", headers=auth)
            assert r.status_code == 200
            cats = r.json()
            names = {c["name"] for c in cats}
            expected = {"task", "update", "cert", "transport", "posture", "system", "inventory"}
            assert expected.issubset(names)


@pytest.mark.asyncio
async def test_archive_query_returns_job(sm, auth, mock_settings):
    """POST /v1/logs/archive/query returns job_id and pending status."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            now = datetime.now(timezone.utc)
            r = await client.post(
                "/v1/logs/archive/query",
                json={
                    "from_ts": now.isoformat(),
                    "to_ts": now.isoformat(),
                },
                headers=auth,
            )
            assert r.status_code == 200
            data = r.json()
            assert "job_id" in data
            assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_policy_delete(sm, auth, mock_settings):
    """DELETE /v1/logs/policy/{scope} deletes a policy."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            # First create a policy via PUT
            r_create = await client.put(
                "/v1/logs/policy",
                json={
                    "scope": "test-scope",
                    "default_level": "debug",
                },
                headers=auth,
            )
            assert r_create.status_code == 200

            # Now delete it
            r = await client.delete("/v1/logs/policy/test-scope", headers=auth)
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "deleted"

            # Verify it's gone (returns default)
            r2 = await client.get("/v1/logs/policy?scope=test-scope", headers=auth)
            assert r2.status_code == 200
            data2 = r2.json()
            # Should return default policy now (created_by=None)
            assert data2["created_by"] is None
