"""Per-host monotonic sequence allocator (durable, transactional)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def allocate(session: AsyncSession, host_id: str) -> int:
    """Atomically allocate the next sequence number for `host_id`.

    Caller must commit the session. Uses SELECT ... FOR UPDATE on Postgres;
    SQLite degrades to BEGIN IMMEDIATE-style locking via implicit lock.
    """
    # Use INSERT...ON CONFLICT to handle the race condition atomically at the DB level
    # Try to increment existing row, or insert new one
    result = await session.execute(
        text(
            """
            INSERT INTO host_sequences (host_id, next_seq)
            VALUES (:host_id, 2)
            ON CONFLICT(host_id) DO UPDATE SET next_seq = next_seq + 1
            RETURNING next_seq - 1 AS seq
            """
        ),
        {"host_id": host_id},
    )
    seq_value = result.scalar()

    if seq_value is None:
        raise AssertionError(f"Failed to allocate sequence for {host_id}")

    return int(seq_value)
