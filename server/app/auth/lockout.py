from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from server.app.models.lockout import LockoutRecord

"""
Account lockout with escalating cooldowns: 5 fails/5min → 1m cooldown;
next fail → 5m cooldown. In-memory dict, with optional DB persistence.
"""


@dataclass
class LockState:
    failure_count: int = 0
    last_failure_time: float | None = None
    lockout_expires_at: float | None = None
    lockout_level: int = 0


class LockoutTracker:
    """In-memory lockout tracker (original sync implementation)."""

    def __init__(self) -> None:
        self._states: dict[str, LockState] = {}

    def record_failure(self, key: str) -> LockState:
        now = time.time()
        state = self._states.get(key, LockState())

        if state.lockout_expires_at and now < state.lockout_expires_at:
            self._states[key] = state
            return state

        was_locked = state.lockout_expires_at is not None

        # Reset failure count if last failure was outside 5-minute window
        if state.last_failure_time is not None and (now - state.last_failure_time) > 300:
            state.failure_count = 0

        state.failure_count += 1
        state.last_failure_time = now

        if state.failure_count >= 5 or was_locked:
            if was_locked:
                state.lockout_level += 1
                state.failure_count = 1
            else:
                state.lockout_level = 1

            cooldown = self._cooldown_for_level(state.lockout_level)
            state.lockout_expires_at = now + cooldown

        self._states[key] = state
        return state

    def record_success(self, key: str) -> None:
        if key in self._states:
            self._states[key] = LockState()

    def is_locked(self, key: str) -> bool:
        if key not in self._states:
            return False

        state = self._states[key]
        now = time.time()

        if state.lockout_expires_at is None:
            return False

        if now >= state.lockout_expires_at:
            self._states[key] = LockState()
            return False

        return True

    def _cooldown_for_level(self, level: int) -> int:
        if level == 1:
            return 60
        return 300


class LockoutTrackerPersistent:
    """DB-backed lockout tracker with optional persistence."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession] | None = None) -> None:
        """Initialize with optional sessionmaker for DB persistence.

        If sessionmaker is None, falls back to in-memory behavior.
        """
        self._sessionmaker = sessionmaker
        self._in_memory: dict[str, LockState] = {}

    async def record_failure(self, key: str) -> LockState:
        """Record a failure for the given key.

        If sessionmaker is configured, persists to DB. Otherwise uses in-memory dict.
        """
        if self._sessionmaker is None:
            return self._record_failure_memory(key)

        from server.app.models.lockout import LockoutRecord

        now_utc = datetime.now(timezone.utc)
        now_ts = time.time()

        async with self._sessionmaker() as session:
            # Read or create record
            rec = await session.scalar(
                select(LockoutRecord).where(LockoutRecord.key == key)
            )

            if rec is None:
                rec = LockoutRecord(
                    key=key,
                    failure_count=0,
                    last_failure_at=None,
                    lockout_expires_at=None,
                    level=0,
                )
                session.add(rec)

            # Check if currently locked
            if rec.lockout_expires_at:
                # Ensure both datetimes are aware for comparison
                expires_at = rec.lockout_expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now_utc < expires_at:
                    await session.commit()
                    return self._record_to_state(rec)

            was_locked = rec.lockout_expires_at is not None

            # Reset failure count if last failure was outside 5-minute window
            if rec.last_failure_at is not None:
                # Ensure both datetimes are aware for comparison
                last_failure = rec.last_failure_at
                if last_failure.tzinfo is None:
                    last_failure = last_failure.replace(tzinfo=timezone.utc)
                elapsed = (now_utc - last_failure).total_seconds()
                if elapsed > 300:
                    rec.failure_count = 0

            rec.failure_count += 1
            rec.last_failure_at = now_utc

            if rec.failure_count >= 5 or was_locked:
                if was_locked:
                    rec.level += 1
                    rec.failure_count = 1
                else:
                    rec.level = 1

                cooldown = self._cooldown_for_level(rec.level)
                rec.lockout_expires_at = datetime.fromtimestamp(
                    now_ts + cooldown, tz=timezone.utc
                )

            await session.commit()
            return self._record_to_state(rec)

    async def record_success(self, key: str) -> None:
        """Record a success for the given key, clearing any lockout."""
        if self._sessionmaker is None:
            if key in self._in_memory:
                self._in_memory[key] = LockState()
            return

        from server.app.models.lockout import LockoutRecord

        async with self._sessionmaker() as session:
            rec = await session.scalar(
                select(LockoutRecord).where(LockoutRecord.key == key)
            )
            if rec is not None:
                await session.delete(rec)
                await session.commit()

    async def is_locked(self, key: str) -> bool:
        """Check if the given key is currently locked."""
        if self._sessionmaker is None:
            return self._is_locked_memory(key)

        from server.app.models.lockout import LockoutRecord

        now_utc = datetime.now(timezone.utc)

        async with self._sessionmaker() as session:
            rec = await session.scalar(
                select(LockoutRecord).where(LockoutRecord.key == key)
            )

            if rec is None:
                return False

            if rec.lockout_expires_at is None:
                return False

            # Ensure both datetimes are aware for comparison
            expires_at = rec.lockout_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if now_utc >= expires_at:
                await session.delete(rec)
                await session.commit()
                return False

            return True

    def _record_failure_memory(self, key: str) -> LockState:
        """In-memory fallback for record_failure."""
        now = time.time()
        state = self._in_memory.get(key, LockState())

        if state.lockout_expires_at and now < state.lockout_expires_at:
            self._in_memory[key] = state
            return state

        was_locked = state.lockout_expires_at is not None

        if state.last_failure_time is not None and (now - state.last_failure_time) > 300:
            state.failure_count = 0

        state.failure_count += 1
        state.last_failure_time = now

        if state.failure_count >= 5 or was_locked:
            if was_locked:
                state.lockout_level += 1
                state.failure_count = 1
            else:
                state.lockout_level = 1

            cooldown = self._cooldown_for_level(state.lockout_level)
            state.lockout_expires_at = now + cooldown

        self._in_memory[key] = state
        return state

    def _is_locked_memory(self, key: str) -> bool:
        """In-memory fallback for is_locked."""
        if key not in self._in_memory:
            return False

        state = self._in_memory[key]
        now = time.time()

        if state.lockout_expires_at is None:
            return False

        if now >= state.lockout_expires_at:
            self._in_memory[key] = LockState()
            return False

        return True

    @staticmethod
    def _record_to_state(rec: LockoutRecord) -> LockState:
        """Convert a DB record to LockState."""
        lockout_expires_ts = None
        if rec.lockout_expires_at:
            lockout_expires_ts = rec.lockout_expires_at.timestamp()

        last_failure_ts = None
        if rec.last_failure_at:
            last_failure_ts = rec.last_failure_at.timestamp()

        return LockState(
            failure_count=rec.failure_count,
            last_failure_time=last_failure_ts,
            lockout_expires_at=lockout_expires_ts,
            lockout_level=rec.level,
        )

    @staticmethod
    def _cooldown_for_level(level: int) -> int:
        if level == 1:
            return 60
        return 300
