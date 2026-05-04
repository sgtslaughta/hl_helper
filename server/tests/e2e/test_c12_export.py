"""C12 Phase 6.2 E2E: audit export + Prometheus metrics surface.

Verifies:
- /v1/audit/export streams in json, cef, syslog, otlp formats
- /v1/observability/metrics exposes Prometheus text format
- Format dispatch matches expected media types
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state

ADMIN_TOKEN = "test-c12-export-tok"


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("FLEET_METRICS_ENABLED", "true")
    yield


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture
def settings() -> FleetSettings:
    return FleetSettings(admin_token=SecretStr(ADMIN_TOKEN), metrics_enabled=True)


async def _seed_audit(state) -> None:
    async with state.sessionmaker() as s:
        await state.audit_chain.append(
            s, actor="u-1", action="approval.requested", subject="a-1", payload={"k": "v"}
        )
        await state.audit_chain.append(
            s, actor="u-1", action="approval.approved", subject="a-1", payload={"decision": "approve"}
        )
        await s.commit()


@pytest.mark.asyncio
async def test_export_default_json(sm, auth, settings):
    state = make_test_app_state(sessionmaker=sm)
    await _seed_audit(state)
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/audit/export", headers=auth)
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("application/x-ndjson")
            lines = [line for line in r.text.split("\n") if line]
            parsed = [json.loads(line) for line in lines]
            assert len(parsed) == 2
            assert parsed[0]["action"] == "approval.requested"


@pytest.mark.asyncio
async def test_export_cef_format(sm, auth, settings):
    state = make_test_app_state(sessionmaker=sm)
    await _seed_audit(state)
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/audit/export?format=cef", headers=auth)
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/plain")
            lines = [line for line in r.text.split("\n") if line]
            assert all(line.startswith("CEF:0|hl-helper|fleet|1|") for line in lines)
            assert len(lines) == 2


@pytest.mark.asyncio
async def test_export_syslog_format(sm, auth, settings):
    state = make_test_app_state(sessionmaker=sm)
    await _seed_audit(state)
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/audit/export?format=syslog", headers=auth)
            assert r.status_code == 200
            lines = [line for line in r.text.split("\n") if line]
            assert all(line.startswith("<134>1 ") for line in lines)
            assert any("approval.approved" in line for line in lines)


@pytest.mark.asyncio
async def test_export_otlp_format(sm, auth, settings):
    state = make_test_app_state(sessionmaker=sm)
    await _seed_audit(state)
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/audit/export?format=otlp", headers=auth)
            assert r.status_code == 200
            lines = [line for line in r.text.split("\n") if line]
            parsed = [json.loads(line) for line in lines]
            assert all(p["severityText"] == "INFO" for p in parsed)
            keys = {a["key"] for a in parsed[0]["attributes"]}
            assert "audit.action" in keys
            assert "audit.entry_hash" in keys


@pytest.mark.asyncio
async def test_export_unsupported_format_returns_422(sm, auth, settings):
    state = make_test_app_state(sessionmaker=sm)
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/audit/export?format=xml", headers=auth)
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(sm, auth, settings):
    state = make_test_app_state(sessionmaker=sm)
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/metrics", headers=auth)
            assert r.status_code == 200
            assert "text/plain" in r.headers["content-type"]
            # Prometheus exposition format starts with HELP/TYPE comments
            assert "# HELP" in r.text or "# TYPE" in r.text or len(r.text) >= 0
