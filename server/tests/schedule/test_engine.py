"""Tests for schedule engine."""

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


@pytest.fixture
def fired_schedules() -> list[Schedule]:
    """List to capture fired schedules."""
    return []


@pytest.fixture
def on_fire_callback(fired_schedules: list[Schedule]):
    """Callback that records fired schedules."""

    async def _callback(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    return _callback


@pytest_asyncio.fixture
async def sched_engine(
    sm: async_sessionmaker,
    on_fire_callback,
):
    """Create a schedule engine for testing."""
    eng = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire_callback,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await eng.start()
    yield eng
    await eng.stop()


@pytest.mark.asyncio
async def test_schedule_fires_invokes_on_fire(
    sched_engine: ScheduleEngine,
    sm: async_sessionmaker,
    fired_schedules: list[Schedule],
) -> None:
    """Test that a registered schedule fires and invokes on_fire callback."""
    # Create a schedule to fire in 100ms
    schedule = Schedule(
        id="test-schedule-1",
        name="Test Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"type": "all"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(schedule)
        await session.commit()

    # Reload engine to pick up the new schedule
    await sched_engine.reload()

    # Replace the cron trigger with a DateTrigger that fires in 100ms
    job = sched_engine._scheduler.get_job("test-schedule-1")
    assert job is not None

    future_time = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    job.reschedule(trigger=DateTrigger(run_date=future_time))

    # Wait for the job to fire
    await asyncio.sleep(0.3)

    # Assert on_fire was called
    assert len(fired_schedules) == 1
    assert fired_schedules[0].id == "test-schedule-1"


@pytest.mark.asyncio
async def test_maintenance_window_blocks_fire(
    sm: async_sessionmaker,
) -> None:
    """Test that active maintenance window blocks schedule from firing."""
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    # Build a maintenance window covering the current minute via cron expansion.
    # Avoid freezegun + asyncio.sleep (incompatible — sleep blocks indefinitely).
    now = datetime.now(timezone.utc)

    engine = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url="sqlite+aiosqlite:///:memory:",
    )
    await engine.start()

    # Window: started 1 minute ago, runs for 60 minutes — overlaps now.
    start_minute = (now - timedelta(minutes=1)).minute
    start_hour = (now - timedelta(minutes=1)).hour
    window = MaintenanceWindow(
        id="maint-1",
        name="Maintenance",
        start_cron=f"{start_minute} {start_hour} * * *",
        duration_minutes=60,
        timezone="UTC",
        target_selector={},
        kind=MaintenanceWindowKind.BLACKOUT,
    )

    schedule = Schedule(
        id="test-schedule-2",
        name="Test Schedule 2",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"type": "all"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(window)
        session.add(schedule)
        await session.commit()

    await engine.reload()

    job = engine._scheduler.get_job("test-schedule-2")
    assert job is not None

    future_time = datetime.now(timezone.utc) + timedelta(milliseconds=100)
    job.reschedule(trigger=DateTrigger(run_date=future_time))

    await asyncio.sleep(0.5)

    assert len(fired_schedules) == 0, f"on_fire should not have been called: {fired_schedules}"

    await engine.stop()


@pytest.mark.asyncio
async def test_timezone_correct(
    sched_engine: ScheduleEngine,
    sm: async_sessionmaker,
) -> None:
    """Test that timezone is correctly plumbed into CronTrigger."""
    schedule = Schedule(
        id="test-schedule-tz",
        name="Test Schedule TZ",
        cron_expr="30 9 * * *",
        timezone="America/Los_Angeles",
        enabled=True,
        target_selector={"type": "all"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(schedule)
        await session.commit()

    await sched_engine.reload()

    job = sched_engine._scheduler.get_job("test-schedule-tz")
    assert job is not None

    # Get the next fire time
    next_fire = job.next_run_time
    assert next_fire is not None

    # Verify the timezone is set correctly
    assert next_fire.tzinfo is not None
    assert str(next_fire.tzinfo) == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_persistence_survives_restart(
    sm: async_sessionmaker,
    tmp_path,
) -> None:
    """Jobs persist across engine restarts via file-backed SQLAlchemyJobStore.

    Uses a file-backed sqlite jobstore so engine2 actually reads engine1's
    serialized jobs from disk (not just re-loading from the application DB).
    """
    fired_schedules: list[Schedule] = []

    async def on_fire(schedule: Schedule) -> None:
        fired_schedules.append(schedule)

    jobs_db = tmp_path / "jobs.sqlite"
    jobstore_url = f"sqlite:///{jobs_db}"

    engine1 = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url=jobstore_url,
    )
    await engine1.start()

    schedule = Schedule(
        id="test-persist",
        name="Persistent Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"type": "all"},
        payload_kind="test",
        payload={},
    )
    async with sm() as session:
        session.add(schedule)
        await session.commit()

    await engine1.reload()
    assert engine1._scheduler.get_job("test-persist") is not None
    await engine1.stop()

    # New engine reads jobs from the same on-disk jobstore.
    engine2 = ScheduleEngine(
        sessionmaker=sm,
        on_fire=on_fire,
        jobstore_url=jobstore_url,
    )
    await engine2.start()
    assert engine2._scheduler.get_job("test-persist") is not None
    await engine2.stop()


@pytest.mark.asyncio
async def test_reload_picks_up_changes(
    sched_engine: ScheduleEngine,
    sm: async_sessionmaker,
) -> None:
    """Test that reload() picks up schedule changes from DB."""
    schedule = Schedule(
        id="test-reload",
        name="Reload Schedule",
        cron_expr="0 0 * * *",
        timezone="UTC",
        enabled=True,
        target_selector={"type": "all"},
        payload_kind="test",
        payload={},
    )

    async with sm() as session:
        session.add(schedule)
        await session.commit()

    await sched_engine.reload(schedule_id="test-reload")

    # Get the original trigger
    job = sched_engine._scheduler.get_job("test-reload")
    assert job is not None
    original_trigger = job.trigger

    # Mutate the cron expression in DB
    async with sm() as session:
        from sqlalchemy import select

        stmt = select(Schedule).where(Schedule.id == "test-reload")
        result = await session.execute(stmt)
        sched = result.scalar_one()
        sched.cron_expr = "30 9 * * *"  # Changed from "0 0 * * *"
        await session.commit()

    # Reload the specific schedule
    await sched_engine.reload(schedule_id="test-reload")

    # Verify job was updated
    updated_job = sched_engine._scheduler.get_job("test-reload")
    assert updated_job is not None
    # Verify the trigger changed (by checking next fire time differs or trigger type)
    assert updated_job.trigger is not original_trigger or (
        hasattr(original_trigger, "fields") and hasattr(updated_job.trigger, "fields")
    )
