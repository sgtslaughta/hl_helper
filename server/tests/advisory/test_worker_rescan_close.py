"""Verify AdvisoryWorker closes RUNNING rescan/resurvey Task rows after match."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.advisory.worker import AdvisoryWorker
from server.app.models.host import Host
from server.app.models.task import Task, TaskKind, TaskRisk, TaskStatus
from server.app.models.task_run import TaskRun, TaskRunStatus
from server.app.settings.config import FleetSettings


@pytest_asyncio.fixture
async def host_id(sm: async_sessionmaker) -> str:
    async with sm() as session:
        host = Host(
            id=str(uuid4()),
            hostname="test",
            display_name="test",
            agent_pubkey=b"\x00" * 32,
            labels={"os": "linux"},
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()
        return host.id


@pytest.mark.asyncio
async def test_close_rescan_tasks_marks_succeeded(sm: async_sessionmaker, host_id: str):
    async with sm() as session:
        task = Task(
            id=str(uuid4()),
            kind=TaskKind.CUSTOM,
            created_by="admin",
            status=TaskStatus.RUNNING,
            payload={"action": "rescan", "host_id": host_id},
            target_selector={"host_ids": [host_id]},
            risk=TaskRisk.LOW,
            requires_approval=False,
        )
        run = TaskRun(
            id=str(uuid4()),
            task_id=task.id,
            host_id=host_id,
            status=TaskRunStatus.RUNNING,
        )
        session.add_all([task, run])
        await session.commit()

    worker = AdvisoryWorker(catalog_sm=sm, fleet_sm=sm, settings=FleetSettings())
    await worker._close_rescan_tasks(host_id, succeeded=True)

    async with sm() as session:
        t_status = (await session.execute(select(Task.status))).scalar_one()
        assert t_status == TaskStatus.SUCCEEDED
        r_status, finished = (
            await session.execute(select(TaskRun.status, TaskRun.finished_at))
        ).one()
        assert r_status == TaskRunStatus.SUCCEEDED
        assert finished is not None


@pytest.mark.asyncio
async def test_close_rescan_tasks_marks_failed(sm: async_sessionmaker, host_id: str):
    async with sm() as session:
        task = Task(
            id=str(uuid4()),
            kind=TaskKind.CUSTOM,
            created_by="admin",
            status=TaskStatus.RUNNING,
            payload={"action": "resurvey", "host_id": host_id},
            target_selector={"host_ids": [host_id]},
            risk=TaskRisk.LOW,
            requires_approval=False,
        )
        session.add(task)
        await session.commit()

    worker = AdvisoryWorker(catalog_sm=sm, fleet_sm=sm, settings=FleetSettings())
    await worker._close_rescan_tasks(host_id, succeeded=False)

    async with sm() as session:
        t_status = (await session.execute(select(Task.status))).scalar_one()
        assert t_status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_close_rescan_tasks_skips_unrelated(sm: async_sessionmaker, host_id: str):
    async with sm() as session:
        unrelated = Task(
            id=str(uuid4()),
            kind=TaskKind.SHELL_EXEC,
            created_by="admin",
            status=TaskStatus.RUNNING,
            payload={"action": "shell", "host_id": host_id, "command": "ls"},
            target_selector={"host_ids": [host_id]},
            risk=TaskRisk.LOW,
            requires_approval=False,
        )
        other_host = Task(
            id=str(uuid4()),
            kind=TaskKind.CUSTOM,
            created_by="admin",
            status=TaskStatus.RUNNING,
            payload={"action": "rescan", "host_id": "different-host"},
            target_selector={"host_ids": ["different-host"]},
            risk=TaskRisk.LOW,
            requires_approval=False,
        )
        session.add_all([unrelated, other_host])
        await session.commit()

    worker = AdvisoryWorker(catalog_sm=sm, fleet_sm=sm, settings=FleetSettings())
    await worker._close_rescan_tasks(host_id, succeeded=True)

    async with sm() as session:
        statuses = sorted(
            r[0] for r in (await session.execute(select(Task.status))).all()
        )
        # both still RUNNING
        assert statuses == [TaskStatus.RUNNING, TaskStatus.RUNNING]
