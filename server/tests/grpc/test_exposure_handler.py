"""Tests for ExposureHandler ingest."""
from __future__ import annotations

from datetime import datetime, timezone

import json
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_ingest_replaces_rows_atomically(sm):
    from server.app.grpc.exposure_handler import ExposureHandler
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        # Pre-existing rows from previous scan — must be replaced
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="OLD-CVE",
                exposure_tier="ACTIVE",
                evidence_json="[]",
                scanned_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            )
        )
        await s.commit()

    derived = [
        {"advisory_id": "CVE-1", "exposure_tier": "NETWORK_EXPOSED",
         "evidence": ["listening tcp/443 (nginx)"]},
        {"advisory_id": "CVE-2", "exposure_tier": "ACTIVE",
         "evidence": ["running pid 1234"]},
    ]
    handler = ExposureHandler(sm)
    await handler.ingest(
        host_id="h-1",
        scanned_at=datetime.now(timezone.utc),
        derived=derived,
    )

    async with sm() as s:
        rows = (
            await s.execute(
                select(HostAdvisoryExposure).where(
                    HostAdvisoryExposure.host_id == "h-1"
                )
            )
        ).scalars().all()
        assert {r.advisory_id for r in rows} == {"CVE-1", "CVE-2"}
        cve1 = next(r for r in rows if r.advisory_id == "CVE-1")
        assert cve1.exposure_tier == "NETWORK_EXPOSED"
        assert json.loads(cve1.evidence_json) == ["listening tcp/443 (nginx)"]


@pytest.mark.asyncio
async def test_ingest_empty_derived_clears_host_rows(sm):
    from server.app.grpc.exposure_handler import ExposureHandler
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        s.add(
            HostAdvisoryExposure(
                host_id="h-1",
                advisory_id="OLD",
                exposure_tier="ACTIVE",
                evidence_json="[]",
                scanned_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            )
        )
        await s.commit()

    handler = ExposureHandler(sm)
    await handler.ingest(
        host_id="h-1", scanned_at=datetime.now(timezone.utc), derived=[]
    )

    async with sm() as s:
        rows = (
            await s.execute(
                select(HostAdvisoryExposure).where(
                    HostAdvisoryExposure.host_id == "h-1"
                )
            )
        ).scalars().all()
        assert rows == []
