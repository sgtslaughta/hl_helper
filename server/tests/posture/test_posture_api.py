"""Tests for posture suppress / unsuppress API endpoints.

@brief Exercises POST /v1/posture/actions/suppress and
POST /v1/posture/actions/unsuppress, including auth guards and
404 handling for unknown finding IDs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.posture.model import Finding
from server.app.posture.store import upsert_finding
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state

ADMIN_TOKEN = "test-posture-api-tok"


@pytest.fixture(autouse=True)
def _set_admin_env(monkeypatch):
    """@brief Inject FLEET_ADMIN_TOKEN into the environment for every test."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)
    yield


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """@brief Authorization header bearing the test admin token."""
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _make_finding(finding_id: str = "test-finding-1") -> Finding:
    """@brief Build a minimal Finding value object for test seeding.

    @param finding_id Stable identifier for the finding.
    @return A frozen Finding dataclass instance.
    """
    return Finding(
        id=finding_id,
        severity="medium",
        title="Test finding",
        summary="A finding created for testing.",
        rule="test_rule",
        subject_kind="global",
    )


# ------------------------------------------------------------------
# suppress
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suppress_returns_404_for_unknown_finding(sm, auth_headers):
    """@brief POST suppress with non-existent finding_id returns 404."""
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/posture/actions/suppress",
                headers=auth_headers,
                json={
                    "finding_id": "nonexistent-id",
                    "reason": "testing",
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(days=1)
                    ).isoformat(),
                },
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_suppress_finding_happy_path(sm, auth_headers):
    """@brief Upsert a finding then suppress it; verify response fields."""
    await upsert_finding(sm, _make_finding("suppress-happy"))

    expires = datetime.now(timezone.utc) + timedelta(days=7)

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/posture/actions/suppress",
                headers=auth_headers,
                json={
                    "finding_id": "suppress-happy",
                    "reason": "accepted risk",
                    "expires_at": expires.isoformat(),
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == "suppress-happy"
            assert body["suppressed_by"] == "admin"
            assert body["suppressed_reason"] == "accepted risk"
            assert body["suppressed_until"] is not None


# ------------------------------------------------------------------
# unsuppress
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsuppress_returns_404_for_unknown_finding(sm, auth_headers):
    """@brief POST unsuppress with non-existent finding_id returns 404."""
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/posture/actions/unsuppress",
                headers=auth_headers,
                json={"finding_id": "nonexistent-id"},
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_unsuppress_finding_happy_path(sm, auth_headers):
    """@brief Upsert + suppress a finding, then unsuppress; verify cleared fields."""
    from server.app.posture.store import suppress_finding

    await upsert_finding(sm, _make_finding("unsuppress-happy"))
    await suppress_finding(
        sm,
        "unsuppress-happy",
        suppressed_by="admin",
        reason="temp",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/posture/actions/unsuppress",
                headers=auth_headers,
                json={"finding_id": "unsuppress-happy"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["id"] == "unsuppress-happy"
            assert body["suppressed_by"] is None
            assert body["suppressed_reason"] is None
            assert body["suppressed_until"] is None


# ------------------------------------------------------------------
# auth guards
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suppress_requires_auth(sm):
    """@brief POST suppress without Authorization header returns 401."""
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/posture/actions/suppress",
                json={
                    "finding_id": "irrelevant",
                    "reason": "nope",
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(days=1)
                    ).isoformat(),
                },
            )
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_unsuppress_requires_auth(sm):
    """@brief POST unsuppress without Authorization header returns 401."""
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/posture/actions/unsuppress",
                json={"finding_id": "irrelevant"},
            )
            assert r.status_code == 401
