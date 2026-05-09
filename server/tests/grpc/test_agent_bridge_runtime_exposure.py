"""Test runtime_exposure arm of AgentToServer."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_agent_bridge_handles_runtime_exposure(
    sm, agent_bridge_servicer
):
    from server.app.models.host import Host
    from server.app.models.host_advisory_exposure import HostAdvisoryExposure
    from sqlalchemy import select

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x00" * 32))
        await s.commit()

    # Drive a synthetic RuntimeExposure through the bridge's test helper.
    bridge = agent_bridge_servicer
    await bridge.handle_runtime_exposure_for_test(
        host_id="h-1",
        scanned_at=datetime.now(timezone.utc),
        scan={
            "processes": [],
            "listeners": [],
            "connections": [],
            "services": [],
            "kernel_modules": [],
            "container_exposure": [],
        },
        host_packages=[],
        advisories=[],
    )

    async with sm() as s:
        rows = (
            await s.execute(
                select(HostAdvisoryExposure).where(
                    HostAdvisoryExposure.host_id == "h-1"
                )
            )
        ).scalars().all()
        # Empty advisories → no derived rows; ingest still runs.
        assert rows == []
