"""Test for concurrent idempotency race condition fix."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.dispatcher.queue import CommandQueue
from server.app.dispatcher.sequence import allocate
from server.app.models.command import Command, CommandRisk, CommandStatus


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_no_duplicates(
    sm: async_sessionmaker,
) -> None:
    """Two concurrent enqueues with same idempotency_key must result in exactly one DB row.

    Simulates the race condition where both threads pass the cache check but only
    one should actually create the row due to DB UNIQUE constraint. The loser should
    catch IntegrityError and re-read the existing row.
    """
    idempotency_key = "concurrent-race-123"
    now = datetime.now(timezone.utc)
    host_id = "host-race"
    queue = CommandQueue()

    # Shared events to coordinate execution
    can_task2_continue = asyncio.Event()

    async def task_1_flow() -> Command:
        async with sm() as session:
            seq = await allocate(session, host_id)
            await session.commit()

        cmd = Command(
            id=str(uuid4()),
            task_run_id="task-1",
            host_id=host_id,
            sequence=seq,
            envelope_bytes=b"envelope-1",
            risk=CommandRisk.LOW,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            status=CommandStatus.QUEUED,
        )

        async with sm() as session:
            result = await queue.enqueue(session, cmd, idempotency_key=idempotency_key)
            await session.commit()
            # Signal task-2 that it can now proceed (enqueue and rollback)
            can_task2_continue.set()
            return result

    async def task_2_flow() -> Command:
        # Wait for task-1 to commit before we start
        await can_task2_continue.wait()

        async with sm() as session:
            seq = await allocate(session, host_id)
            await session.commit()

        cmd = Command(
            id=str(uuid4()),
            task_run_id="task-2",
            host_id=host_id,
            sequence=seq,
            envelope_bytes=b"envelope-2",
            risk=CommandRisk.LOW,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            status=CommandStatus.QUEUED,
        )

        async with sm() as session:
            result = await queue.enqueue(session, cmd, idempotency_key=idempotency_key)
            await session.commit()
            return result

    # Clear the cache to ensure both hit the race (or at least task-2 does)
    queue._idempotency_cache.clear()

    # Run sequentially but async: task-1 commits, then task-2 tries to enqueue
    # Task-2 will hit the IntegrityError and should recover by reading task-1's row
    results = await asyncio.gather(
        task_1_flow(),
        task_2_flow(),
    )

    # Both should return the same command_id (one created, one re-read)
    result_ids = [r.id for r in results]
    assert result_ids[0] == result_ids[1], (
        f"concurrent enqueues with same key returned different command IDs: "
        f"{result_ids[0]} vs {result_ids[1]}"
    )

    # Verify exactly one row exists in DB with this idempotency_key
    async with sm() as session:
        rows = (
            await session.execute(
                select(Command).where(Command.idempotency_key == idempotency_key)
            )
        ).scalars().all()
        assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
        assert rows[0].id == result_ids[0]
