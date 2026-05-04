"""C12 Phase 6.1 E2E: posture finding lifecycle.

Trigger -> rank -> suppress -> expiry -> reactivate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from server.app.api.app import create_app
from server.app.models.host import Host
from server.app.posture.inspector import run_inspection
from server.app.posture.model import PostureFindingRow
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state

ADMIN_TOKEN = "test-c12-e2e-tok"


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)
    yield


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture
def settings() -> FleetSettings:
    return FleetSettings(admin_token=SecretStr(ADMIN_TOKEN))


@pytest.mark.asyncio
async def test_c12_posture_lifecycle(sm, auth, settings):
    """Full lifecycle: inspector -> findings ranked -> suppress -> expiry -> reactivate."""
    # Seed: enrolled host with no heartbeat (triggers hosts_unreachable_recently)
    async with sm() as s:
        s.add(Host(id="h-c12", hostname="h-c12", agent_pubkey=b"\x00" * 32, last_seen_at=None))
        await s.commit()

    # Run inspector — emits findings for repo state (multiple findings expected)
    state = make_test_app_state(sessionmaker=sm)
    await run_inspection(state.sessionmaker, settings=settings)

    async with sm() as s:
        rows = (await s.execute(select(PostureFindingRow))).scalars().all()
    assert len(rows) >= 3, f"expected several findings, got {len(rows)}"
    severities = {r.severity for r in rows}
    assert severities & {"info", "medium", "high", "critical"}

    # GET /v1/posture returns ranked findings
    app = create_app()
    app.state.app_state = state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=settings,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/posture", headers=auth)
            assert r.status_code == 200
            body = r.json()
            findings = body["findings"]
            assert len(findings) >= 3
            # Ranking: critical/high should rank above info
            sev_ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            ranks = [sev_ranks[f["severity"]] for f in findings]
            assert ranks == sorted(ranks)

            target_id = "hosts_never_checked_in"
            assert any(f["id"] == target_id for f in findings)

            # Suppress for 1 minute
            until = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
            r2 = await c.post(
                "/v1/posture/actions/suppress",
                headers=auth,
                json={
                    "finding_id": target_id,
                    "expires_at": until,
                    "reason": "investigating",
                },
            )
            assert r2.status_code == 200
            assert r2.json()["suppressed_until"] is not None

            # GET with default (suppressed=false) hides it
            r3 = await c.get("/v1/posture", headers=auth)
            assert r3.status_code == 200
            assert all(f["id"] != target_id for f in r3.json()["findings"])

            # GET with include_suppressed=true exposes it
            r4 = await c.get("/v1/posture?include_suppressed=true", headers=auth)
            assert any(f["id"] == target_id for f in r4.json()["findings"])

            # Force expiry by direct DB update
            async with sm() as s:
                row = await s.scalar(
                    select(PostureFindingRow).where(PostureFindingRow.id == target_id)
                )
                row.suppressed_until = datetime.now(timezone.utc) - timedelta(minutes=1)
                await s.commit()

            # Re-run inspector clears expired suppressions
            await run_inspection(state.sessionmaker, settings=settings)
            r5 = await c.get("/v1/posture", headers=auth)
            assert any(f["id"] == target_id for f in r5.json()["findings"])
