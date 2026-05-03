"""Tests for DB-backed durable idempotency cache in CommandQueue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.dispatcher.queue import CommandQueue
from server.app.dispatcher.sequence import allocate
from server.app.models.command import Command, CommandRisk, CommandStatus


@pytest.mark.asyncio
async def test_enqueue_idempotency_key_persists_to_db(sm: async_sessionmaker) -> None:
    """enqueue with idempotency_key stores it in the Command row."""
    queue = CommandQueue()
    now = datetime.now(timezone.utc)
    host_id = "host-1"
    idempotency_key = "test-key-1"

    # Create and enqueue a command with an idempotency_key
    async with sm() as session:
        seq = await allocate(session, host_id)
        await session.commit()

    cmd = Command(
        id=str(uuid4()),
        task_run_id="task-1",
        host_id=host_id,
        sequence=seq,
        envelope_bytes=b"test",
        risk=CommandRisk.LOW,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        status=CommandStatus.QUEUED,
    )

    async with sm() as session:
        result = await queue.enqueue(session, cmd, idempotency_key=idempotency_key)
        await session.commit()

    # Verify the idempotency_key was stored in the DB
    async with sm() as session:
        from sqlalchemy import select
        row = (
            await session.execute(
                select(Command).where(Command.id == result.id)
            )
        ).scalar_one()
        assert row.idempotency_key == idempotency_key


@pytest.mark.asyncio
async def test_enqueue_durable_idempotency_different_queues(sm: async_sessionmaker) -> None:
    """Two separate CommandQueue instances return same Command when using same idempotency_key.

    This test verifies that idempotency is durable across process restarts by
    simulating two queue instances (representing different processes) that share
    the same database. Both should return the same Command when given the same key.
    """
    idempotency_key = "durable-key-123"
    now = datetime.now(timezone.utc)
    host_id = "host-persistent"

    # First queue instance (represents process 1)
    queue1 = CommandQueue()

    # Allocate sequence and create first command
    async with sm() as session:
        seq1 = await allocate(session, host_id)
        await session.commit()

    cmd1 = Command(
        id=str(uuid4()),
        task_run_id="task-1",
        host_id=host_id,
        sequence=seq1,
        envelope_bytes=b"test1",
        risk=CommandRisk.LOW,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        status=CommandStatus.QUEUED,
    )

    # Enqueue with idempotency_key in process 1
    async with sm() as session:
        result1 = await queue1.enqueue(session, cmd1, idempotency_key=idempotency_key)
        await session.commit()

    cmd1_id = result1.id

    # Simulate process restart: create a new queue instance
    queue2 = CommandQueue()

    # Allocate a new sequence (as if we were about to create a new command)
    async with sm() as session:
        seq2 = await allocate(session, host_id)
        await session.commit()

    cmd2 = Command(
        id=str(uuid4()),
        task_run_id="task-2",
        host_id=host_id,
        sequence=seq2,
        envelope_bytes=b"test2",
        risk=CommandRisk.LOW,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        status=CommandStatus.QUEUED,
    )

    # Try to enqueue the same idempotency_key in process 2
    # Should get back the original command (cmd1), not cmd2
    async with sm() as session:
        result2 = await queue2.enqueue(session, cmd2, idempotency_key=idempotency_key)
        await session.commit()

    # Verify we got the original command back
    assert result2.id == cmd1_id
    assert result2.id != cmd2.id

    # Verify cmd2 was never actually persisted
    async with sm() as session:
        from sqlalchemy import select
        cmd2_in_db = (
            await session.execute(
                select(Command).where(Command.id == cmd2.id)
            )
        ).scalar_one_or_none()
        assert cmd2_in_db is None
