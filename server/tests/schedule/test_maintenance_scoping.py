"""Tests for maintenance window target_selector scoping in schedule engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models.maintenance_window import MaintenanceWindow, MaintenanceWindowKind
from server.app.models.schedule import Schedule
from server.app.schedule.engine import ScheduleEngine


@pytest_asyncio.fixture
async def sched_engine_with_callback(sm: async_sessionmaker):
    """Create a schedule engine with a callback to capture fired schedules."""
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    engine = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await engine.start()
    yield engine, fired_schedules
    await engine.stop()


@pytest.mark.asyncio
async def test_blackout_universal_blocks_any_schedule(
    sm: async_sessionmaker,
) -> None:
    """Blackout with target_selector={} (universal) blocks any schedule."""
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    engine = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await engine.start()

    # Create universal blackout window
    now = datetime.now(timezone.utc)
    start_minute = (now - timedelta(minutes=1)).minute
    start_hour = (now - timedelta(minutes=1)).hour
    window = MaintenanceWindow(
        id="maint-universal",
        name="Universal Blackout",
        start_cron=f"{start_minute} {start_hour} * * *",
        duration_minutes=60,
        timezone="UTC",
        target_selector={},  # Universal: blocks everything
        kind=MaintenanceWindowKind.BLACKOUT,
    )

    schedule = Schedule(
        id="sched-1",
        name="Schedule 1",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"group_id": "g-prod"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(window)
        session.add(schedule)
        await session.commit()

    await engine.reload()

    job = engine._scheduler.get_job("sched-1")
    assert job is not None

    future_time = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    job.reschedule(trigger=DateTrigger(run_date=future_time))

    await asyncio.sleep(0.5)

    assert (
        len(fired_schedules) == 0
    ), "Universal blackout should block schedule regardless of selector"

    await engine.stop()


@pytest.mark.asyncio
async def test_blackout_group_id_does_not_block_different_group(
    sm: async_sessionmaker,
) -> None:
    """Blackout with target_selector={'group_id': 'g-prod'} does NOT block {'group_id': 'g-stage'}."""
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    engine = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await engine.start()

    # Create blackout for g-prod only
    now = datetime.now(timezone.utc)
    start_minute = (now - timedelta(minutes=1)).minute
    start_hour = (now - timedelta(minutes=1)).hour
    window = MaintenanceWindow(
        id="maint-prod",
        name="Prod Blackout",
        start_cron=f"{start_minute} {start_hour} * * *",
        duration_minutes=60,
        timezone="UTC",
        target_selector={"group_id": "g-prod"},
        kind=MaintenanceWindowKind.BLACKOUT,
    )

    # Schedule targets g-stage (different group)
    schedule = Schedule(
        id="sched-stage",
        name="Stage Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"group_id": "g-stage"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(window)
        session.add(schedule)
        await session.commit()

    await engine.reload()

    job = engine._scheduler.get_job("sched-stage")
    assert job is not None

    future_time = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    job.reschedule(trigger=DateTrigger(run_date=future_time))

    await asyncio.sleep(0.5)

    assert (
        len(fired_schedules) == 1
    ), "Blackout for g-prod should NOT block schedule for g-stage"

    await engine.stop()


@pytest.mark.asyncio
async def test_blackout_group_id_blocks_same_group(
    sm: async_sessionmaker,
) -> None:
    """Blackout with target_selector={'group_id': 'g-prod'} DOES block {'group_id': 'g-prod'}."""
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    engine = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await engine.start()

    # Create blackout for g-prod
    now = datetime.now(timezone.utc)
    start_minute = (now - timedelta(minutes=1)).minute
    start_hour = (now - timedelta(minutes=1)).hour
    window = MaintenanceWindow(
        id="maint-prod",
        name="Prod Blackout",
        start_cron=f"{start_minute} {start_hour} * * *",
        duration_minutes=60,
        timezone="UTC",
        target_selector={"group_id": "g-prod"},
        kind=MaintenanceWindowKind.BLACKOUT,
    )

    # Schedule also targets g-prod
    schedule = Schedule(
        id="sched-prod",
        name="Prod Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"group_id": "g-prod"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(window)
        session.add(schedule)
        await session.commit()

    await engine.reload()

    job = engine._scheduler.get_job("sched-prod")
    assert job is not None

    future_time = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    job.reschedule(trigger=DateTrigger(run_date=future_time))

    await asyncio.sleep(0.5)

    assert (
        len(fired_schedules) == 0
    ), "Blackout for g-prod should block schedule for g-prod"

    await engine.stop()


@pytest.mark.asyncio
async def test_blackout_host_id_blocks_same_host(
    sm: async_sessionmaker,
) -> None:
    """Blackout with target_selector={'host_id': 'h-1'} blocks {'host_id': 'h-1'}, not h-2."""
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    engine = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await engine.start()

    now = datetime.now(timezone.utc)
    start_minute = (now - timedelta(minutes=1)).minute
    start_hour = (now - timedelta(minutes=1)).hour

    # Create blackout for h-1
    window = MaintenanceWindow(
        id="maint-h1",
        name="H1 Blackout",
        start_cron=f"{start_minute} {start_hour} * * *",
        duration_minutes=60,
        timezone="UTC",
        target_selector={"host_id": "h-1"},
        kind=MaintenanceWindowKind.BLACKOUT,
    )

    # Schedule 1 targets h-1 (should be blocked)
    schedule1 = Schedule(
        id="sched-h1",
        name="H1 Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"host_id": "h-1"},
        payload_kind="test",
        payload={},
    )

    # Schedule 2 targets h-2 (should fire)
    schedule2 = Schedule(
        id="sched-h2",
        name="H2 Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"host_id": "h-2"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(window)
        session.add(schedule1)
        session.add(schedule2)
        await session.commit()

    await engine.reload()

    for sched_id in ["sched-h1", "sched-h2"]:
        job = engine._scheduler.get_job(sched_id)
        assert job is not None
        future_time = datetime.now(timezone.utc) + timedelta(milliseconds=100)
        job.reschedule(trigger=DateTrigger(run_date=future_time))

    await asyncio.sleep(0.5)

    assert (
        len(fired_schedules) == 1
    ), "Only sched-h2 should fire; sched-h1 blocked by blackout"
    assert fired_schedules[0].id == "sched-h2"

    await engine.stop()
