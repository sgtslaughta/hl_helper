"""Tests for persistent LockoutTracker with DB backing."""

from __future__ import annotations

from typing import AsyncIterator

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.auth.lockout import LockoutTrackerPersistent
from server.app.models import LockoutRecord
from server.app.models.base import Base as BaseModel
from server.app.db.session import make_engine, make_sessionmaker


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine and initialize all tables."""
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield e
    await e.dispose()


@pytest.fixture
async def sm(engine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    return make_sessionmaker(engine)


@pytest.fixture
async def session(sm) -> AsyncIterator[AsyncSession]:
    """Create a fresh session for each test."""
    async with sm() as s:
        yield s
        await s.rollback()


class TestLockoutTrackerPersistent:
    """Tests for persistent LockoutTracker with DB backing."""

    @freeze_time("2026-05-03 12:00:00")
    async def test_five_failures_persisted_across_restart(self, sm: async_sessionmaker) -> None:
        """Five failures persisted in DB; new tracker instance reads from DB."""
        tracker = LockoutTrackerPersistent(sessionmaker=sm)
        key = "user:123"

        # Record 5 failures with first tracker
        for _ in range(5):
            await tracker.record_failure(key)

        # Verify locked
        assert await tracker.is_locked(key)

        # Simulate restart: create new tracker from same sessionmaker
        tracker2 = LockoutTrackerPersistent(sessionmaker=sm)
        assert await tracker2.is_locked(key), "Second tracker should still see lockout from DB"

    @freeze_time("2026-05-03 12:00:00")
    async def test_sixth_failure_escalates_from_db(self, sm: async_sessionmaker) -> None:
        """Sixth failure after 1-min cooldown should escalate to 5-min lockout."""
        tracker = LockoutTrackerPersistent(sessionmaker=sm)
        key = "user:456"

        # Record 5 failures
        for _ in range(5):
            await tracker.record_failure(key)
        assert await tracker.is_locked(key)

        # Wait 1 min 30 sec and record 6th failure
        with freeze_time("2026-05-03 12:01:30"):
            await tracker.record_failure(key)
            assert await tracker.is_locked(key)

        # Should still be locked at 12:05
        with freeze_time("2026-05-03 12:05:00"):
            assert await tracker.is_locked(key)

        # Should be unlocked at 12:06:30 (5 min cooldown expires)
        with freeze_time("2026-05-03 12:06:30"):
            assert not await tracker.is_locked(key)

    @freeze_time("2026-05-03 12:00:00")
    async def test_success_deletes_record(self, sm: async_sessionmaker, session: AsyncSession) -> None:
        """Recording success should delete the lockout record."""
        tracker = LockoutTrackerPersistent(sessionmaker=sm)
        key = "user:789"

        # Record 3 failures
        for _ in range(3):
            await tracker.record_failure(key)

        # Record success
        await tracker.record_success(key)

        # Check record is deleted from DB
        result = await session.scalar(
            select(LockoutRecord).where(LockoutRecord.key == key)
        )
        assert result is None

    @freeze_time("2026-05-03 12:00:00")
    async def test_sliding_window_persists(self, sm: async_sessionmaker) -> None:
        """Sliding window logic should work across tracker instances."""
        tracker = LockoutTrackerPersistent(sessionmaker=sm)
        key = "user:999"

        # Record 3 failures
        for _ in range(3):
            await tracker.record_failure(key)

        # Create new tracker instance (simulating restart)
        tracker2 = LockoutTrackerPersistent(sessionmaker=sm)

        # Advance time past 5-min window
        with freeze_time("2026-05-03 12:05:01"):
            await tracker2.record_failure(key)
            # Record from DB should show failure_count reset to 1 (window expired)
            async with sm() as s:
                rec = await s.scalar(
                    select(LockoutRecord).where(LockoutRecord.key == key)
                )
                assert rec is not None
                assert rec.failure_count == 1
