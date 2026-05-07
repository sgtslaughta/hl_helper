"""Tests for Task, TaskRun, and Command models."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.models import Task, TaskRun, Command, Host


@pytest.mark.asyncio
async def test_task_create(sm):
    """Test basic Task creation with defaults."""
    async with sm() as session:
        t = Task(
            id="t-1",
            kind="reboot",
            risk="med",
            payload={"delay_s": 60},
            target_selector={"host_ids": ["h-1"]},
        )
        session.add(t)
        await session.commit()
        got = await session.scalar(select(Task).where(Task.id == "t-1"))
        assert got.kind == "reboot"
        assert got.status == "pending"  # default
        assert got.requires_approval is False


@pytest.mark.asyncio
async def test_task_run_unique_per_host(sm):
    """Test that (task_id, host_id) must be unique."""
    async with sm() as session:
        h = Host(id="h-1", hostname="h", agent_pubkey=b"\x00" * 32)
        t = Task(
            id="t-2",
            kind="reboot",
            risk="low",
            payload={},
            target_selector={},
        )
        session.add_all([h, t])
        await session.commit()

        r1 = TaskRun(id="r-1", task_id="t-2", host_id="h-1", status="pending")
        session.add(r1)
        await session.commit()

        r2 = TaskRun(id="r-2", task_id="t-2", host_id="h-1", status="pending")
        session.add(r2)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_command_sequence_unique_per_host(sm):
    """Test that (host_id, sequence) must be unique."""
    async with sm() as session:
        h = Host(id="h-2", hostname="h2", agent_pubkey=b"\x00" * 32)
        t = Task(
            id="t-3",
            kind="shell_exec",
            risk="high",
            payload={},
            target_selector={},
        )
        session.add_all([h, t])
        await session.flush()

        r = TaskRun(id="r-3", task_id="t-3", host_id="h-2", status="pending")
        session.add(r)
        await session.flush()

        now = datetime.now(timezone.utc)
        c1 = Command(
            id="c-1",
            task_run_id="r-3",
            host_id="h-2",
            sequence=1,
            envelope_bytes=b"x",
            risk="high",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            status="queued",
        )
        session.add(c1)
        await session.commit()

        # Reuse sequence=1 for same host → IntegrityError
        c2 = Command(
            id="c-2",
            task_run_id="r-3",
            host_id="h-2",
            sequence=1,
            envelope_bytes=b"y",
            risk="high",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            status="queued",
        )
        session.add(c2)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_command_sequence_per_host_independent(sm):
    """Test that seq=1 on host A and seq=1 on host B both allowed."""
    async with sm() as session:
        ha = Host(id="ha", hostname="a", agent_pubkey=b"\x00" * 32)
        hb = Host(id="hb", hostname="b", agent_pubkey=b"\x00" * 32)
        t = Task(
            id="t-4",
            kind="reboot",
            risk="low",
            payload={},
            target_selector={},
        )
        session.add_all([ha, hb, t])
        await session.flush()

        ra = TaskRun(id="ra", task_id="t-4", host_id="ha", status="pending")
        rb = TaskRun(id="rb", task_id="t-4", host_id="hb", status="pending")
        session.add_all([ra, rb])
        await session.flush()

        now = datetime.now(timezone.utc)
        ca = Command(
            id="ca",
            task_run_id="ra",
            host_id="ha",
            sequence=1,
            envelope_bytes=b"a",
            risk="low",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            status="queued",
        )
        cb = Command(
            id="cb",
            task_run_id="rb",
            host_id="hb",
            sequence=1,
            envelope_bytes=b"b",
            risk="low",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            status="queued",
        )
        session.add_all([ca, cb])
        await session.commit()  # no error


def test_task_kind_agent_update_exists():
    """Test that TaskKind.AGENT_UPDATE exists with value 'agent_update'."""
    from server.app.models.task import TaskKind
    assert TaskKind.AGENT_UPDATE.value == "agent_update"
