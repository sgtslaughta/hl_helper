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
