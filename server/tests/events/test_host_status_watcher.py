"""Tests for the host status watcher (online→offline timeout flips + ticker emit)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.events.bus import Bus
from server.app.events.host_status_watcher import scan_offline_transitions
from server.app.events.ticker import TICKER_CHANNEL
from server.app.models.host import Host


async def _mk_host(
    sm: async_sessionmaker,
    *,
    hostname: str,
    last_seen_ago_s: float | None,
    status: str = "healthy",
    interval_s: int = 30,
) -> str:
    hid = str(uuid4())
    async with sm() as s:
        last_seen = (
            datetime.now(timezone.utc) - timedelta(seconds=last_seen_ago_s)
            if last_seen_ago_s is not None
            else None
        )
        s.add(
            Host(
                id=hid,
                hostname=hostname,
                agent_pubkey=b"\x00" * 32,
                last_seen_at=last_seen,
                status=status,
                heartbeat_interval_s=interval_s,
            )
        )
        await s.commit()
    return hid


@pytest_asyncio.fixture
async def collected(sm: async_sessionmaker):
    """Collect ticker events into a list for assertion."""
    bus = Bus()
    received: list[dict] = []

    async def consume():
        async for ev in bus.subscribe(TICKER_CHANNEL):
            received.append(dict(ev.payload))

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    yield bus, received
    task.cancel()


@pytest.mark.asyncio
async def test_flips_stale_host_to_offline(
    sm: async_sessionmaker, collected
) -> None:
    bus, received = collected
    hid = await _mk_host(sm, hostname="alpha", last_seen_ago_s=200, interval_s=30)

    flipped = await scan_offline_transitions(sm, bus)

    assert hid in flipped
    async with sm() as s:
        h = await s.get(Host, hid)
        assert h is not None and h.status == "offline"
    await asyncio.sleep(0.02)
    assert any(e["type"] == "host" and e["severity"] == "warn" for e in received)
    assert any("alpha" in e["text"] for e in received)


@pytest.mark.asyncio
async def test_keeps_fresh_host(
    sm: async_sessionmaker, collected
) -> None:
    bus, received = collected
    await _mk_host(sm, hostname="beta", last_seen_ago_s=10, interval_s=30)

    flipped = await scan_offline_transitions(sm, bus)
    assert flipped == []
    await asyncio.sleep(0.02)
    assert received == []


@pytest.mark.asyncio
async def test_idempotent_no_repeat_when_already_offline(
    sm: async_sessionmaker, collected
) -> None:
    bus, received = collected
    await _mk_host(
        sm,
        hostname="gamma",
        last_seen_ago_s=500,
        status="offline",
        interval_s=30,
    )

    flipped = await scan_offline_transitions(sm, bus)
    assert flipped == []
    await asyncio.sleep(0.02)
    assert received == []


@pytest.mark.asyncio
async def test_handles_host_with_no_last_seen(
    sm: async_sessionmaker, collected
) -> None:
    """Brand-new host with no heartbeat yet is not flipped (no transition info)."""
    bus, received = collected
    await _mk_host(sm, hostname="delta", last_seen_ago_s=None, interval_s=30)

    flipped = await scan_offline_transitions(sm, bus)
    assert flipped == []
    await asyncio.sleep(0.02)
    assert received == []
