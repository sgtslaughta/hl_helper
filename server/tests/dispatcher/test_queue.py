"""Tests for durable command queue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.dispatcher.queue import CommandQueue
from server.app.dispatcher.sequence import allocate
from server.app.models.command import Command, CommandRisk, CommandStatus


@pytest.fixture
def queue() -> CommandQueue:
    """Create a fresh CommandQueue instance per test."""
    return CommandQueue()


async def _make_command(
    sm: async_sessionmaker,
    host_id: str,
    task_run_id: str = "task-1",
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Command:
    """Helper to create a Command in the database."""
    if issued_at is None:
        issued_at = datetime.now(timezone.utc)
    if expires_at is None:
        expires_at = issued_at + timedelta(hours=1)

    async with sm() as session:
        seq = await allocate(session, host_id)
        cmd = Command(
            id=str(uuid4()),
            task_run_id=task_run_id,
            host_id=host_id,
            sequence=seq,
            envelope_bytes=b"test",
            risk=CommandRisk.LOW,
            issued_at=issued_at,
            expires_at=expires_at,
            status=CommandStatus.QUEUED,
        )
        session.add(cmd)
        await session.commit()
    return cmd


@pytest.mark.asyncio
async def test_enqueue_persists(sm: async_sessionmaker, queue: CommandQueue) -> None:
    """enqueue persists command; new session sees it."""
    from sqlalchemy import select

    # Create a fresh command object (not yet in DB)
    now = datetime.now(timezone.utc)
    host_id = "host-1"

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

    # Enqueue in a session and commit
    async with sm() as session:
        result = await queue.enqueue(session, cmd)
        await session.commit()

    # Verify new session sees the command
    async with sm() as session:
        row = (
            await session.execute(
                select(Command).where(Command.id == result.id)
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.status == CommandStatus.QUEUED


@pytest.mark.asyncio
async def test_pop_returns_fifo_per_host(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """pop returns QUEUED commands in sequence order (FIFO) per host."""
    # Create 3 commands for host-1 in sequence order
    cmd1 = await _make_command(sm, "host-1", task_run_id="task-1")
    cmd2 = await _make_command(sm, "host-1", task_run_id="task-2")
    cmd3 = await _make_command(sm, "host-1", task_run_id="task-3")

    async with sm() as session:
        # Pop should return in FIFO order
        popped1 = await queue.pop(session, "host-1")
        popped2 = await queue.pop(session, "host-1")
        popped3 = await queue.pop(session, "host-1")
        await session.commit()

    assert popped1 is not None
    assert popped2 is not None
    assert popped3 is not None
    assert popped1.id == cmd1.id
    assert popped2.id == cmd2.id
    assert popped3.id == cmd3.id


@pytest.mark.asyncio
async def test_pop_transitions_queued_to_in_flight(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """pop transitions status from QUEUED to IN_FLIGHT."""
    cmd = await _make_command(sm, "host-1")

    async with sm() as session:
        popped = await queue.pop(session, "host-1")
        await session.commit()

    assert popped is not None
    assert popped.status == CommandStatus.IN_FLIGHT

    # Verify in database
    async with sm() as session:
        from sqlalchemy import select

        row = (
            await session.execute(
                select(Command).where(Command.id == cmd.id)
            )
        ).scalar_one()
        assert row.status == CommandStatus.IN_FLIGHT


@pytest.mark.asyncio
async def test_pop_returns_none_when_empty(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """pop returns None when no QUEUED commands."""
    async with sm() as session:
        result = await queue.pop(session, "host-1")
        await session.commit()

    assert result is None


@pytest.mark.asyncio
async def test_peek_does_not_change_state(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """peek returns oldest QUEUED without changing status."""
    cmd = await _make_command(sm, "host-1")

    async with sm() as session:
        peeked = await queue.peek(session, "host-1")
        await session.commit()

    assert peeked is not None
    assert peeked.id == cmd.id
    assert peeked.status == CommandStatus.QUEUED

    # Verify database still has QUEUED
    async with sm() as session:
        from sqlalchemy import select

        row = (
            await session.execute(
                select(Command).where(Command.id == cmd.id)
            )
        ).scalar_one()
        assert row.status == CommandStatus.QUEUED


@pytest.mark.asyncio
async def test_pop_host_isolation(sm: async_sessionmaker, queue: CommandQueue) -> None:
    """pop on host A doesn't return host B's commands."""
    cmd_a = await _make_command(sm, "host-a", task_run_id="task-a")
    cmd_b = await _make_command(sm, "host-b", task_run_id="task-b")

    async with sm() as session:
        popped_a = await queue.pop(session, "host-a")
        popped_b = await queue.pop(session, "host-b")
        await session.commit()

    assert popped_a is not None
    assert popped_b is not None
    assert popped_a.id == cmd_a.id
    assert popped_b.id == cmd_b.id


@pytest.mark.asyncio
async def test_expire_overdue_marks_expired(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """expire_overdue marks QUEUED rows with expires_at < now as EXPIRED."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)

    # Create one expired command
    cmd_expired = await _make_command(
        sm, "host-1", issued_at=past, expires_at=past + timedelta(minutes=30)
    )
    # Create one that hasn't expired
    cmd_fresh = await _make_command(
        sm, "host-1", issued_at=now, expires_at=now + timedelta(hours=1)
    )

    async with sm() as session:
        count = await queue.expire_overdue(session, now=now)
        await session.commit()

    assert count == 1

    # Verify the expired command is EXPIRED
    async with sm() as session:
        from sqlalchemy import select

        expired_row = (
            await session.execute(
                select(Command).where(Command.id == cmd_expired.id)
            )
        ).scalar_one()
        fresh_row = (
            await session.execute(
                select(Command).where(Command.id == cmd_fresh.id)
            )
        ).scalar_one()

        assert expired_row.status == CommandStatus.EXPIRED
        assert fresh_row.status == CommandStatus.QUEUED


@pytest.mark.asyncio
async def test_expire_overdue_skips_in_flight(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """expire_overdue doesn't touch IN_FLIGHT commands even if expired."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)

    cmd = await _make_command(
        sm, "host-1", issued_at=past, expires_at=past + timedelta(minutes=30)
    )

    # Move to IN_FLIGHT
    async with sm() as session:
        await queue.pop(session, "host-1")
        await session.commit()

    # Try to expire
    async with sm() as session:
        count = await queue.expire_overdue(session, now=now)
        await session.commit()

    assert count == 0

    # Verify it's still IN_FLIGHT
    async with sm() as session:
        from sqlalchemy import select

        row = (
            await session.execute(
                select(Command).where(Command.id == cmd.id)
            )
        ).scalar_one()
        assert row.status == CommandStatus.IN_FLIGHT


@pytest.mark.asyncio
async def test_idempotent_enqueue_same_key_returns_same_command(
    sm: async_sessionmaker, queue: CommandQueue
) -> None:
    """enqueue with same idempotency_key returns same Command id (process-local dict)."""
    now = datetime.now(timezone.utc)
    host_id = "host-1"

    # Create first command
    async with sm() as session:
        seq1 = await allocate(session, host_id)
        await session.commit()

    cmd1 = Command(
        id=str(uuid4()),
        task_run_id="task-1",
        host_id=host_id,
        sequence=seq1,
        envelope_bytes=b"test",
        risk=CommandRisk.LOW,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        status=CommandStatus.QUEUED,
    )

    async with sm() as session:
        result1 = await queue.enqueue(session, cmd1, idempotency_key="key-1")
        await session.commit()

    # Create second command with different id but same key
    async with sm() as session:
        seq2 = await allocate(session, host_id)
        await session.commit()

    cmd2 = Command(
        id=str(uuid4()),
        task_run_id="task-2",
        host_id=host_id,
        sequence=seq2,
        envelope_bytes=b"test",
        risk=CommandRisk.LOW,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        status=CommandStatus.QUEUED,
    )

    async with sm() as session:
        result2 = await queue.enqueue(session, cmd2, idempotency_key="key-1")
        await session.commit()

    # Should return the same command due to idempotency cache
    assert result1.id == result2.id
    assert result1.id == cmd1.id  # Should be cmd1, not cmd2
    assert result2.id != cmd2.id  # cmd2 should not have been used
