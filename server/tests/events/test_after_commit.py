"""Tests for deferred event publishing until after transaction commit."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from server.app.events.bus import Bus
from server.app.events.after_commit import publish_after_commit


@pytest.mark.asyncio
async def test_publish_fires_after_commit(sm) -> None:
    """Subscribe to bus; call publish_after_commit; before commit assert no event delivered; commit → event delivered."""
    bus = Bus()

    # Subscribe to events
    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("commands")
        async for event in sub:
            events.append(event)
            if len(events) >= 1:
                break

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)  # Let subscriber start

    # Get a fresh session
    async with sm() as session:
        # Schedule publish via after_commit (not awaiting publish directly)
        publish_after_commit(
            session,
            bus,
            "commands",
            {"event": "test.event", "data": "value"}
        )

        # Before commit, no event should be delivered
        await asyncio.sleep(0.01)
        assert len(events) == 0, "Event published before commit"

        # Commit the transaction
        await session.commit()

    # Wait for event to be delivered
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # After commit, event should be delivered
    assert len(events) >= 1, "Event not delivered after commit"
    assert events[0].channel == "commands"
    assert events[0].payload["event"] == "test.event"
    assert events[0].payload["data"] == "value"


@pytest.mark.asyncio
async def test_publish_dropped_on_rollback(sm) -> None:
    """Subscribe; publish_after_commit; rollback → no event; subsequent commit on same session → still no event."""
    bus = Bus()

    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("commands")
        async for event in sub:
            events.append(event)
            if len(events) >= 2:
                break

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    async with sm() as session:
        # Schedule publish
        publish_after_commit(
            session,
            bus,
            "commands",
            {"event": "first.event"}
        )

        # Rollback instead of commit
        await session.rollback()

    # After rollback, no event should be delivered
    await asyncio.sleep(0.05)
    assert len(events) == 0, "Event published despite rollback"

    # Now do another publish and commit on a new session
    async with sm() as session2:
        publish_after_commit(
            session2,
            bus,
            "commands",
            {"event": "second.event"}
        )
        await session2.commit()

    # Wait for events
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Should only see the second event, not the first (rolled-back) one
    event_names = [e.payload.get("event") for e in events]
    assert "first.event" not in event_names, "Rolled-back event was published"
    assert "second.event" in event_names, "Second event not published"


@pytest.mark.asyncio
async def test_multiple_publishes_one_commit_batched(sm) -> None:
    """Register 3 publishes, commit once → all 3 delivered in order."""
    bus = Bus()

    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("commands")
        async for event in sub:
            events.append(event)
            if len(events) >= 3:
                break

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    async with sm() as session:
        # Register 3 publishes
        publish_after_commit(session, bus, "commands", {"n": 1})
        publish_after_commit(session, bus, "commands", {"n": 2})
        publish_after_commit(session, bus, "commands", {"n": 3})

        # Before commit, no events
        await asyncio.sleep(0.01)
        assert len(events) == 0

        # Commit
        await session.commit()

    # Wait for all 3 events
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # All 3 should be delivered in order
    assert len(events) >= 3, f"Expected 3+ events, got {len(events)}"
    assert events[0].payload["n"] == 1
    assert events[1].payload["n"] == 2
    assert events[2].payload["n"] == 3


@pytest.mark.asyncio
async def test_idempotent_registration(sm) -> None:
    """Register publish, commit, register another, commit → second batch fires correctly (no duplicate firing)."""
    bus = Bus()

    events: list[Any] = []

    async def collect_events():
        sub = bus.subscribe("commands")
        async for event in sub:
            events.append(event)
            if len(events) >= 2:
                break

    collect_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.01)

    # First batch
    async with sm() as session1:
        publish_after_commit(session1, bus, "commands", {"batch": 1, "n": "a"})
        await session1.commit()

    # Small delay to ensure first commit fires
    await asyncio.sleep(0.05)

    # Second batch on a fresh session
    async with sm() as session2:
        publish_after_commit(session2, bus, "commands", {"batch": 2, "n": "b"})
        await session2.commit()

    # Wait for events
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Should have exactly 2 events, one from each commit
    assert len(events) >= 2, f"Expected 2+ events, got {len(events)}"
    assert events[0].payload["batch"] == 1
    assert events[1].payload["batch"] == 2
    # Ensure no duplicate publishing of the first event
    batch_1_events = [e for e in events if e.payload.get("batch") == 1]
    assert len(batch_1_events) == 1, f"First event published {len(batch_1_events)} times"
