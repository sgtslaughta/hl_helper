"""Tests for per-host monotonic sequence allocator."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.dispatcher.sequence import allocate


@pytest.mark.asyncio
async def test_first_allocation_returns_1(
    sm: async_sessionmaker,
) -> None:
    """Fresh host → 1."""
    async with sm() as session:
        seq = await allocate(session, "host-1")
        await session.commit()

        assert seq == 1


@pytest.mark.asyncio
async def test_concurrent_allocations_strictly_monotonic(
    sm: async_sessionmaker,
) -> None:
    """100 sequential allocates per host return 1..100."""
    results = []

    async with sm() as session:
        for _ in range(100):
            seq = await allocate(session, "host-1")
            results.append(seq)
        await session.commit()

    assert results == list(range(1, 101))


@pytest.mark.asyncio
async def test_per_host_independence(
    sm: async_sessionmaker,
) -> None:
    """host A and host B both start at 1."""
    async with sm() as session:
        seq_a = await allocate(session, "host-a")
        seq_b = await allocate(session, "host-b")
        await session.commit()

        assert seq_a == 1
        assert seq_b == 1


@pytest.mark.asyncio
async def test_concurrent_per_host_no_dupes_no_gaps(
    sm: async_sessionmaker,
) -> None:
    """asyncio.gather(allocate(...) for _ in range(50)) with separate sessions; sort results == range(1, 51)."""

    async def allocate_once(host_id: str) -> int:
        """Allocate once with its own session."""
        async with sm() as session:
            seq = await allocate(session, host_id)
            await session.commit()
            return seq

    # Launch 50 concurrent allocations for the same host
    results = await asyncio.gather(
        *[allocate_once("host-concurrent") for _ in range(50)]
    )

    # Sort and verify no duplicates and no gaps
    sorted_results = sorted(results)
    assert sorted_results == list(range(1, 51)), (
        f"Expected range 1..50, got {sorted_results}"
    )


@pytest.mark.asyncio
async def test_sequence_durable_across_session_close(
    sm: async_sessionmaker,
) -> None:
    """Allocate 3 in one session, commit, close; new session sees next_seq=4."""
    # Session 1: allocate 3 times, commit, and close
    async with sm() as session:
        seq1 = await allocate(session, "host-durable")
        seq2 = await allocate(session, "host-durable")
        seq3 = await allocate(session, "host-durable")
        await session.commit()
        # Session implicitly closed here

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    # Session 2: new session should get seq=4 (next_seq is durable)
    async with sm() as session:
        seq4 = await allocate(session, "host-durable")
        await session.commit()

        assert seq4 == 4


@pytest.mark.asyncio
async def test_updated_at_bumps_on_each_allocation(
    sm: async_sessionmaker,
) -> None:
    """updated_at timestamp is bumped on each allocation."""
    from sqlalchemy import select
    from server.app.models.host_sequence import HostSequence

    # First allocation
    async with sm() as session:
        seq1 = await allocate(session, "host-timestamp")
        await session.commit()

        assert seq1 == 1

    # Get first updated_at
    async with sm() as session:
        row1 = (
            await session.execute(
                select(HostSequence).where(HostSequence.host_id == "host-timestamp")
            )
        ).scalar_one()
        updated_at_1 = row1.updated_at

    # Delay long enough for second-resolution timestamp to differ
    await asyncio.sleep(1.1)

    async with sm() as session:
        seq2 = await allocate(session, "host-timestamp")
        await session.commit()

        assert seq2 == 2

    # Get second updated_at
    async with sm() as session:
        row2 = (
            await session.execute(
                select(HostSequence).where(HostSequence.host_id == "host-timestamp")
            )
        ).scalar_one()
        updated_at_2 = row2.updated_at

    # Verify updated_at was bumped (second is later than first)
    assert updated_at_2 > updated_at_1
