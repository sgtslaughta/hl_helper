"""Tests for advisories API endpoints.

@brief Exercises GET /v1/advisories, GET /v1/advisories/{id},
GET /v1/hosts/{host_id}/advisories, suppress/unsuppress, and
GET /v1/posture/summary.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from server.app.api.app import create_app
from server.app.models.advisory import Advisory
from server.app.models.host import Host
from server.app.models.host_advisory import HostAdvisory
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state

ADMIN_TOKEN = "test-advisories-api-tok"


@pytest.fixture(autouse=True)
def _set_admin_env(monkeypatch):
    """@brief Inject FLEET_ADMIN_TOKEN into the environment for every test."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)
    yield


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """@brief Authorization header bearing the test admin token."""
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture
async def test_host(sm):
    """@brief Create a test host for use in tests."""
    async with sm() as session:
        host = Host(
            id="test-host-1",
            hostname="test-host",
            agent_pubkey=b"0" * 32,
        )
        session.add(host)
        await session.commit()
        return host


@pytest.mark.asyncio
async def test_list_advisories_empty_returns_empty_list(sm, auth_headers):
    """@brief GET /v1/advisories with no advisories returns empty list."""
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/v1/advisories", headers=auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert data["advisories"] == []
            assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_advisories_filters_by_severity_and_kev(sm, auth_headers):
    """@brief List advisories filters by severity and kev flag."""
    async with sm() as session:
        # Create 3 advisories with different severities
        adv1 = Advisory(
            id="CVE-2024-001",
            summary="Critical vuln",
            severity="critical",
            kev=True,
            epss=0.9,
            modified=datetime.now(timezone.utc),
        )
        adv2 = Advisory(
            id="CVE-2024-002",
            summary="Medium vuln",
            severity="medium",
            kev=False,
            epss=0.5,
            modified=datetime.now(timezone.utc),
        )
        adv3 = Advisory(
            id="CVE-2024-003",
            summary="High vuln",
            severity="high",
            kev=False,
            epss=0.7,
            modified=datetime.now(timezone.utc),
        )
        session.add_all([adv1, adv2, adv3])
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Test filter by severity=high
            r = await c.get(
                "/v1/advisories", headers=auth_headers, params={"severity": "high"}
            )
            assert r.status_code == 200
            data = r.json()
            assert len(data["advisories"]) == 1
            assert data["advisories"][0]["id"] == "CVE-2024-003"

            # Test filter by kev=true
            r = await c.get(
                "/v1/advisories", headers=auth_headers, params={"kev": "true"}
            )
            assert r.status_code == 200
            data = r.json()
            assert len(data["advisories"]) == 1
            assert data["advisories"][0]["id"] == "CVE-2024-001"


@pytest.mark.asyncio
async def test_get_advisory_404(sm, auth_headers):
    """@brief GET /v1/advisories/{id} returns 404 if missing."""
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/v1/advisories/nonexistent", headers=auth_headers)
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_advisory_returns_with_affected_packages(sm, auth_headers):
    """@brief GET /v1/advisories/{id} includes affected packages."""
    from server.app.models.advisory import AffectedPackage

    async with sm() as session:
        adv = Advisory(
            id="CVE-2024-042",
            summary="Test advisory",
            severity="high",
            kev=False,
            modified=datetime.now(timezone.utc),
        )
        pkg = AffectedPackage(
            advisory_id="CVE-2024-042",
            ecosystem="npm",
            package="test-pkg",
        )
        session.add(adv)
        session.add(pkg)
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/v1/advisories/CVE-2024-042", headers=auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert data["id"] == "CVE-2024-042"
            assert len(data["affected_packages"]) == 1
            assert data["affected_packages"][0]["package"] == "test-pkg"


@pytest.mark.asyncio
async def test_list_host_advisories_only_open_by_default(sm, auth_headers, test_host):
    """@brief GET /v1/hosts/{host_id}/advisories filters to open by default."""
    host_id = test_host.id

    async with sm() as session:
        adv = Advisory(
            id="CVE-2024-100",
            summary="Host advisory",
            severity="critical",
            kev=False,
            modified=datetime.now(timezone.utc),
        )
        host_adv_open = HostAdvisory(
            host_id=host_id,
            advisory_id="CVE-2024-100",
            package="vuln-pkg",
            ecosystem="npm",
            current_version="1.0.0",
            status="open",
        )
        host_adv_fixed = HostAdvisory(
            host_id=host_id,
            advisory_id="CVE-2024-100",
            package="fixed-pkg",
            ecosystem="npm",
            current_version="2.0.0",
            status="fixed",
        )
        session.add(adv)
        session.add(host_adv_open)
        session.add(host_adv_fixed)
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get(
                f"/v1/hosts/{host_id}/advisories", headers=auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["status"] == "open"


@pytest.mark.asyncio
async def test_suppress_and_unsuppress_round_trip(sm, auth_headers, test_host):
    """@brief POST suppress then unsuppress round-trip."""
    host_id = test_host.id

    async with sm() as session:
        adv = Advisory(
            id="CVE-2024-200",
            summary="Suppressible advisory",
            severity="medium",
            kev=False,
            modified=datetime.now(timezone.utc),
        )
        host_adv = HostAdvisory(
            host_id=host_id,
            advisory_id="CVE-2024-200",
            package="pkg",
            ecosystem="npm",
            current_version="1.0.0",
            status="open",
        )
        session.add(adv)
        session.add(host_adv)
        await session.commit()
        ha_id = host_adv.id

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Suppress
            expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            r = await c.post(
                f"/v1/hosts/{host_id}/advisories/{ha_id}/suppress",
                headers=auth_headers,
                json={"reason": "Testing suppression", "expires_at": expires},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "suppressed"

            # Unsuppress
            r = await c.post(
                f"/v1/hosts/{host_id}/advisories/{ha_id}/unsuppress", headers=auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "open"


@pytest.mark.asyncio
async def test_posture_summary_counts_by_severity(sm, auth_headers, test_host):
    """@brief GET /v1/posture/summary returns severity counts."""
    host_id = test_host.id

    async with sm() as session:
        # Create advisories of different severities
        for severity, count in [("critical", 2), ("high", 3), ("medium", 1)]:
            for i in range(count):
                adv = Advisory(
                    id=f"CVE-{severity.upper()}-{i}",
                    summary=f"{severity} advisory",
                    severity=severity,
                    kev=severity == "critical",
                    modified=datetime.now(timezone.utc),
                )
                session.add(adv)
                ha = HostAdvisory(
                    host_id=host_id,
                    advisory_id=f"CVE-{severity.upper()}-{i}",
                    package="pkg",
                    ecosystem="npm",
                    current_version="1.0.0",
                    status="open",
                )
                session.add(ha)
        await session.commit()

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        app = create_app()
        app.state.app_state = make_test_app_state(sessionmaker=sm)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/v1/posture/summary", headers=auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert data["totals"]["critical"] == 2
            assert data["totals"]["high"] == 3
            assert data["totals"]["medium"] == 1
            assert data["totals"]["low"] == 0
            assert data["kev_count"] == 2
