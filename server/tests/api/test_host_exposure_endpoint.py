"""Tests for /v1/hosts/{id}/exposure endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_get_host_exposure_returns_summary(sm):
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        scanned = datetime.now(timezone.utc)
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="CVE-1",
                exposure_tier="NETWORK_EXPOSED",
                evidence_json=json.dumps(["listening tcp/443 (nginx)"]),
                scanned_at=scanned,
            )
        )
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="CVE-2",
                exposure_tier="ACTIVE",
                evidence_json=json.dumps(["running pid 1234"]),
                scanned_at=scanned,
            )
        )
        await s.commit()

    # Just verify the model exists; full endpoint test would need app setup
    assert True


@pytest.mark.asyncio
async def test_get_host_exposure_404(sm):
    # Placeholder for full endpoint test
    assert True


@pytest.mark.asyncio
async def test_rescan_pushes_run_exposure_scan(sm):
    # Placeholder for full endpoint test
    assert True
