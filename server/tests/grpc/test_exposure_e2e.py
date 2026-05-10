"""End-to-end exposure ingest + scoring."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_exposure_ingest_then_score_reflects_tier(sm):
    """Ingest a synthetic exposure scan, run the scorer helpers, verify the
    NETWORK_EXPOSED tier multiplied advisory CVSS by 2.0."""
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure
    from server.app.posture.risk.scorers.vulnerabilities import (
        _apply_exposure_weight,
        _resolve_tier,
    )

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="CVE-1",
                exposure_tier="NETWORK_EXPOSED",
                evidence_json=json.dumps(["listening tcp/443 (nginx)"]),
                scanned_at=datetime.now(timezone.utc),
            )
        )
        await s.commit()

    async with sm() as s:
        rows = (
            await s.execute(
                select(HostAdvisoryExposure).where(HostAdvisoryExposure.host_id == "h-1")
            )
        ).scalars().all()

    tier = _resolve_tier(
        advisory_id="CVE-1",
        exposures=rows,
        now=datetime.now(timezone.utc),
        scan_interval_seconds=6 * 3600,
    )
    assert tier == "NETWORK_EXPOSED"

    weighted = _apply_exposure_weight(
        base=10.0, tier=tier,
        multipliers={"NETWORK_EXPOSED": 2.0, "ACTIVE": 1.5, "INSTALLED_ONLY": 0.5, "UNKNOWN": 1.0},
    )
    assert weighted == 20.0


@pytest.mark.asyncio
async def test_stale_exposure_returns_unknown(sm):
    """Exposure older than 2x scan interval treated as UNKNOWN."""
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure
    from server.app.posture.risk.scorers.vulnerabilities import _resolve_tier

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        old = datetime.now(timezone.utc) - timedelta(hours=24)
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="CVE-1",
                exposure_tier="ACTIVE",
                evidence_json="[]",
                scanned_at=old,
            )
        )
        await s.commit()

    async with sm() as s:
        rows = (
            await s.execute(
                select(HostAdvisoryExposure).where(HostAdvisoryExposure.host_id == "h-1")
            )
        ).scalars().all()

    tier = _resolve_tier(
        advisory_id="CVE-1",
        exposures=rows,
        now=datetime.now(timezone.utc),
        scan_interval_seconds=6 * 3600,
    )
    assert tier == "UNKNOWN"
