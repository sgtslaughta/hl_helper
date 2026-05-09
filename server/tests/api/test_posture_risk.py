"""GET /v1/hosts/{id}/risk basic tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.models import Host
from server.app.models.host_risk import HostRisk
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    """Set admin token in environment."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")


@pytest.fixture
def admin_headers():
    """Return admin auth headers."""
    return {"Authorization": "Bearer test-tok"}


@pytest.fixture
def mock_settings():
    """Return mocked settings with admin token."""
    return FleetSettings(admin_token=SecretStr("test-tok"))


@pytest.mark.asyncio
async def test_get_host_risk_404_unknown_host(admin_headers, sm, mock_settings):
    """GET /v1/hosts/{id}/risk returns 404 for unknown host."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                "/v1/hosts/00000000-0000-0000-0000-000000000000/risk",
                headers=admin_headers,
            )
            assert r.status_code == 404
            assert r.json()["detail"] == "host_not_found"


@pytest.mark.asyncio
async def test_get_host_risk_503_no_risk_data(admin_headers, sm, mock_settings, host_id):
    """GET /v1/hosts/{id}/risk returns 503 when risk data unavailable and recomputer unavailable."""
    app = create_app()
    state = mock.MagicMock()
    state.sessionmaker = sm
    state.risk_registry = None
    state.risk_recomputer = None  # No recomputer to compute risk
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/hosts/{host_id}/risk",
                headers=admin_headers,
            )
            assert r.status_code == 503
            assert r.json()["detail"] == "risk_unavailable"


@pytest.mark.asyncio
async def test_get_host_risk_200_with_cached_data(admin_headers, sm, mock_settings, host_id):
    """GET /v1/hosts/{id}/risk returns 200 with cached risk data."""
    # Insert a HostRisk row with test data
    async with sm() as session:
        host_risk = HostRisk(
            host_id=host_id,
            score=42,
            level="medium",
            confidence=0.85,
            pillars={
                "identity": {
                    "score": 50,
                    "confidence": 0.8,
                    "weight": 0.3,
                    "drivers": [],
                    "coverage_notes": [],
                },
                "detection": {
                    "score": 40,
                    "confidence": 0.9,
                    "weight": 0.3,
                    "drivers": [],
                    "coverage_notes": [],
                },
            },
            computed_at=datetime.now(timezone.utc),
            inputs_hash="abc123",
            floor_triggered=False,
        )
        session.add(host_risk)
        await session.commit()

    app = create_app()
    state = mock.MagicMock()
    state.sessionmaker = sm
    state.risk_registry = None
    state.risk_recomputer = None
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/hosts/{host_id}/risk",
                headers=admin_headers,
            )
            assert r.status_code == 200
            body = r.json()
            assert body["host_id"] == host_id
            assert body["score"] == 42
            assert body["level"] == "medium"
            assert body["confidence"] == 0.85
            assert isinstance(body["pillars"], list)
            assert len(body["pillars"]) == 2
            assert all("name" in p for p in body["pillars"])
            assert all("label" in p for p in body["pillars"])
            assert all("score" in p for p in body["pillars"])
