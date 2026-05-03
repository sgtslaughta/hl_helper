"""Tests for /v1/approvals API endpoint."""

from __future__ import annotations

from unittest import mock

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.settings.config import FleetSettings


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


@pytest.mark.asyncio
async def test_list_approvals_admin_gated_401():
    """GET /v1/approvals without auth returns 401."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/approvals")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_approval_201(auth, sm, mock_settings):
    """POST /v1/approvals returns 201 with created approval."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            body = {
                "subject_type": "command",
                "subject_id": "c-1",
                "policy": "two_person",
                "requester_id": "u-1",
            }
            r = await c.post("/v1/approvals", json=body, headers=auth)
            assert r.status_code == 201
            d = r.json()
            assert d["state"] == "pending"
            assert d["subject_id"] == "c-1"


@pytest.mark.asyncio
async def test_two_person_same_principal_rejected_200(auth, sm, mock_settings):
    """Two-person approval with same principal rejected; returns 200 with decision."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-2",
                    "policy": "two_person",
                    "requester_id": "u-1",
                },
                headers=auth,
            )
            aid = r.json()["id"]
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decider_id": "u-1", "decision": "approve"},
                headers=auth,
            )
            assert r2.status_code == 200
            assert r2.json()["rejected_reason"] == "same_principal"
            assert r2.json()["approved"] is False


@pytest.mark.asyncio
async def test_two_person_different_principal_approves(auth, sm, mock_settings):
    """Two-person approval with different principal approves."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-1",
                    "policy": "two_person",
                    "requester_id": "u-r",
                },
                headers=auth,
            )
            aid = r.json()["id"]
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decider_id": "u-d", "decision": "approve"},
                headers=auth,
            )
            assert r2.json()["approved"] is True
            assert r2.json()["state"] == "approved"


@pytest.mark.asyncio
async def test_decide_unknown_id_404(auth, sm, mock_settings):
    """POST /v1/approvals/{id}/decisions with unknown id returns 404."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals/does-not-exist/decisions",
                json={"decider_id": "u-d", "decision": "approve"},
                headers=auth,
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_filter_by_state(auth, sm, mock_settings):
    """GET /v1/approvals?state=approved filters by state."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create two pending approvals
            for i in range(2):
                await c.post(
                    "/v1/approvals",
                    json={
                        "subject_type": "task",
                        "subject_id": f"t-{i}",
                        "policy": "single",
                        "requester_id": "u-r",
                    },
                    headers=auth,
                )
            # Approve only the first
            approvals = (await c.get("/v1/approvals", headers=auth)).json()
            first_id = approvals[0]["id"]
            await c.post(
                f"/v1/approvals/{first_id}/decisions",
                json={"decider_id": "u-d", "decision": "approve"},
                headers=auth,
            )
            r = await c.get("/v1/approvals?state=approved", headers=auth)
            states = {a["state"] for a in r.json()}
            assert states == {"approved"}


@pytest.mark.asyncio
async def test_ttl_minutes_clamps_to_max(auth, sm, mock_settings):
    """ttl_minutes > 1440 returns 422."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-x",
                    "policy": "single",
                    "requester_id": "u-r",
                    "ttl_minutes": 99999,
                },
                headers=auth,
            )
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_ttl_minutes_minimum_clamps(auth, sm, mock_settings):
    """ttl_minutes <= 0 returns 422."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-y",
                    "policy": "single",
                    "requester_id": "u-r",
                    "ttl_minutes": 0,
                },
                headers=auth,
            )
            assert r.status_code == 422
