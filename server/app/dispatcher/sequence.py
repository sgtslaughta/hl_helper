"""Per-host monotonic sequence allocator via atomic INSERT...ON CONFLICT.

Provides allocate() for distributed command ordering without external locks.
Uses single SQL statement (INSERT...ON CONFLICT DO UPDATE) to be atomic on
both SQLite and Postgres. Each call returns next sequential number for a host,
durable across sessions. Caller must commit() the session for changes to persist.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def allocate(session: AsyncSession, host_id: str) -> int:
    """Atomically allocate the next sequence number for `host_id`.

    Implementation: INSERT ... ON CONFLICT (host_id) DO UPDATE SET
    next_seq = next_seq + 1 RETURNING next_seq - 1. This single statement
    is atomic on both SQLite (via implicit row lock) and Postgres
    (via row lock on conflict).

    Caller must commit the session.
    """
    # Use INSERT...ON CONFLICT to handle the race condition atomically at the DB level
    # Try to increment existing row, or insert new one
    result = await session.execute(
        text(
            """
            INSERT INTO host_sequences (host_id, next_seq, updated_at)
            VALUES (:host_id, 2, CURRENT_TIMESTAMP)
            ON CONFLICT(host_id) DO UPDATE SET next_seq = next_seq + 1, updated_at = CURRENT_TIMESTAMP
            RETURNING next_seq - 1 AS seq
            """
        ),
        {"host_id": host_id},
    )
    seq_value = result.scalar()

    if seq_value is None:
        raise AssertionError(f"Failed to allocate sequence for {host_id}")

    return int(seq_value)
