"""Background sweeper: mark expired Commands + Tasks as failed/timeout.

Agents enforce per-command timeout locally, but agents can also crash,
disconnect, or never receive a command. The server therefore needs its
own deadline: when Command.expires_at is in the past and no Result has
arrived, flip Command.status -> EXPIRED and roll up the parent Task to
FAILED (or PARTIAL if other hosts succeeded).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from server.app.models import Command, Task, TaskRun
from server.app.models.command import CommandStatus
from server.app.models.result import Result
from server.app.models.task import TaskStatus

log = structlog.get_logger(__name__)


_SWEEP_INTERVAL_S = 10


async def run_command_sweeper(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Run forever: every 10s, fail any commands past their deadline."""
    log.info("command_sweeper.started")
    try:
        while True:
            await asyncio.sleep(_SWEEP_INTERVAL_S)
            try:
                await _sweep_once(sessionmaker)
            except Exception as e:
                log.exception("command_sweeper.tick_failed", error=str(e))
    except asyncio.CancelledError:
        log.info("command_sweeper.cancelled")
        raise


async def _sweep_once(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        # Find live commands that are past deadline.
        live_states = (CommandStatus.QUEUED, CommandStatus.IN_FLIGHT)
        rows = (
            await session.execute(
                select(Command).where(
                    Command.status.in_(live_states),
                    Command.expires_at < now,
                )
            )
        ).scalars().all()

        if not rows:
            return

        affected_task_ids: set[str] = set()
        for cmd in rows:
            # Skip if a Result already exists (race with normal handler).
            r = (
                await session.execute(
                    select(Result.id).where(Result.command_id == cmd.id).limit(1)
                )
            ).scalar_one_or_none()
            if r is not None:
                continue

            cmd.status = CommandStatus.EXPIRED
            tr = await session.get(TaskRun, cmd.task_run_id)
            if tr is not None and tr.task_id:
                affected_task_ids.add(tr.task_id)

        # Roll up affected Tasks based on existing Result statuses.
        for task_id in affected_task_ids:
            task = await session.get(Task, task_id)
            if task is None or task.status not in (
                TaskStatus.PENDING,
                TaskStatus.APPROVED,
                TaskStatus.RUNNING,
            ):
                continue
            runs = (
                await session.execute(select(TaskRun).where(TaskRun.task_id == task.id))
            ).scalars().all()
            statuses: list[str | None] = []
            for run in runs:
                latest = (
                    await session.execute(
                        select(Result)
                        .where(Result.command_id.in_(
                            select(Command.id).where(Command.task_run_id == run.id)
                        ))
                        .order_by(Result.sequence.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest is not None:
                    statuses.append(latest.status)
                    continue
                # No result, but command may have expired.
                cmd_state = (
                    await session.execute(
                        select(Command.status)
                        .where(Command.task_run_id == run.id)
                        .order_by(Command.sequence.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                statuses.append("timeout" if cmd_state == CommandStatus.EXPIRED else None)

            if any(s is None for s in statuses):
                task.status = TaskStatus.RUNNING
            elif all(s == "ok" for s in statuses):
                task.status = TaskStatus.SUCCEEDED
            elif all(s != "ok" for s in statuses):
                task.status = TaskStatus.FAILED
            else:
                task.status = TaskStatus.PARTIAL

        await session.commit()
        log.info(
            "command_sweeper.expired",
            commands=len(rows),
            tasks=len(affected_task_ids),
        )
