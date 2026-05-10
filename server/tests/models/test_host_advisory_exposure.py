"""Tests for HostAdvisoryExposure model."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_host_advisory_exposure_persists(sm):
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="CVE-2026-1234",
                exposure_tier="NETWORK_EXPOSED",
                evidence_json=json.dumps(["listening tcp/443 (nginx pid 1234)"]),
                scanned_at=datetime.now(timezone.utc),
            )
        )
        await s.commit()

    async with sm() as s:
        row = (
            await s.execute(
                select(HostAdvisoryExposure).where(
                    HostAdvisoryExposure.host_id == "h-1",
                    HostAdvisoryExposure.advisory_id == "CVE-2026-1234",
                )
            )
        ).scalar_one()
        assert row.exposure_tier == "NETWORK_EXPOSED"
        evidence = json.loads(row.evidence_json)
        assert evidence == ["listening tcp/443 (nginx pid 1234)"]
