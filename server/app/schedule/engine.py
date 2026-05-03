"""Schedule engine for APScheduler integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from zoneinfo import ZoneInfo
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models.maintenance_window import MaintenanceWindow, MaintenanceWindowKind
from server.app.models.schedule import Schedule

logger = logging.getLogger(__name__)

# Module-level registry of live ScheduleEngine instances keyed by engine_id.
# APScheduler's SQLAlchemyJobStore serializes job targets; bound methods that
# capture engines/sessions are not serializable. The job stores engine_id and
# a top-level fire function resolves the engine at firing time.
_engine_registry: dict[str, "ScheduleEngine"] = {}


async def _dispatch_fire(engine_id: str, schedule_id: str) -> None:
    """Top-level serializable job target. Routes to the registered engine."""
    eng = _engine_registry.get(engine_id)
    if eng is None:
        logger.warning("ScheduleEngine %s not registered; skipping %s", engine_id, schedule_id)
        return
    await eng._fire(schedule_id)


class ScheduleEngine:
    """Async schedule engine using APScheduler with SQLAlchemy persistence."""

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker,
        on_fire: Callable[[Schedule], Awaitable[None]],
        jobstore_url: str | None = None,
    ) -> None:
        """Initialize schedule engine.

        Args:
            sessionmaker: Async session factory.
            on_fire: Async callback invoked when a schedule fires.
            jobstore_url: SQLAlchemy connection URL for persistence. Defaults to in-memory.
        """
        self._sessionmaker = sessionmaker
        self._on_fire = on_fire
        # APScheduler's SQLAlchemyJobStore requires a synchronous SQLAlchemy URL.
        # Strip async drivers (e.g. "+aiosqlite", "+asyncpg") so callers can pass
        # the same URL used for the application engine.
        raw_url = jobstore_url or "sqlite:///:memory:"
        for async_driver in ("+aiosqlite", "+asyncpg", "+asyncmy"):
            raw_url = raw_url.replace(async_driver, "")
        self._jobstore_url = raw_url
        self._scheduler = AsyncIOScheduler()
        self._engine_id = f"sched-{id(self):x}"
        _engine_registry[self._engine_id] = self

    async def start(self) -> None:
        """Load all enabled schedules and register cron jobs."""
        # Configure the SQLAlchemy job store
        jobstore = SQLAlchemyJobStore(url=self._jobstore_url)
        self._scheduler.add_jobstore(jobstore, alias="default")

        # Start the scheduler
        self._scheduler.start()

        # Load all enabled schedules from DB
        async with self._sessionmaker() as session:
            stmt = select(Schedule).where(Schedule.enabled.is_(True))
            result = await session.execute(stmt)
            schedules = result.scalars().all()

        # Register each schedule as a cron job
        for schedule in schedules:
            await self._register_job(schedule)

    async def stop(self) -> None:
        """Stop the scheduler and remove this engine from the global registry."""
        try:
            self._scheduler.shutdown(wait=False)
        finally:
            _engine_registry.pop(self._engine_id, None)

    async def reload(self, schedule_id: str | None = None) -> None:
        """Reload schedule(s) from DB and replace job(s).

        Args:
            schedule_id: If provided, reload only this schedule. Otherwise reload all.
        """
        async with self._sessionmaker() as session:
            if schedule_id:
                stmt = select(Schedule).where(Schedule.id == schedule_id)
                result = await session.execute(stmt)
                schedules = result.scalars().all()
            else:
                stmt = select(Schedule).where(Schedule.enabled.is_(True))
                result = await session.execute(stmt)
                schedules = result.scalars().all()

        # Remove old jobs and register new ones
        for schedule in schedules:
            job = self._scheduler.get_job(schedule.id)
            if job:
                self._scheduler.remove_job(schedule.id)
            if schedule.enabled:
                await self._register_job(schedule)

    async def _register_job(self, schedule: Schedule) -> None:
        """Register a single schedule as a cron job.

        Args:
            schedule: The Schedule model to register.
        """
        try:
            tz = ZoneInfo(schedule.timezone)
        except Exception:
            logger.warning("Schedule %s: invalid timezone %r — falling back to UTC",
                           schedule.id, schedule.timezone)
            tz = ZoneInfo("UTC")

        trigger = CronTrigger.from_crontab(schedule.cron_expr, timezone=tz)

        self._scheduler.add_job(
            _dispatch_fire,
            trigger=trigger,
            args=(self._engine_id, schedule.id),
            id=schedule.id,
            coalesce=True,
            misfire_grace_time=300,
            replace_existing=True,
        )

    async def _fire(self, schedule_id: str) -> None:
        """Internal job target invoked by APScheduler.

        Checks for active maintenance windows and skips firing if blocked.
        Updates last_run_at and invokes the on_fire callback.

        Args:
            schedule_id: The ID of the schedule to fire.
        """
        async with self._sessionmaker() as session:
            # Fetch the schedule
            stmt = select(Schedule).where(Schedule.id == schedule_id)
            result = await session.execute(stmt)
            schedule = result.scalar_one_or_none()

            if not schedule:
                logger.warning(f"Schedule {schedule_id} not found")
                return

            # Check for active maintenance windows (BLACKOUT kind).
            # TODO(plan-c2): scope blackouts by intersection of window.target_selector
            # and schedule.target_selector. Today, ANY active blackout silences
            # ALL schedules — that is broader than the spec intends.
            now = datetime.now(timezone.utc)
            maint_stmt = select(MaintenanceWindow).where(
                MaintenanceWindow.kind == MaintenanceWindowKind.BLACKOUT
            )
            maint_result = await session.execute(maint_stmt)
            windows = maint_result.scalars().all()

            # Check if any window overlaps with now
            for window in windows:
                try:
                    tz = ZoneInfo(window.timezone)
                except Exception:
                    logger.warning("MaintenanceWindow %s: invalid timezone %r — UTC",
                                   window.id, window.timezone)
                    tz = ZoneInfo("UTC")

                # Parse window start cron and compute end time
                cron_trigger = CronTrigger.from_crontab(window.start_cron, timezone=tz)

                # Get the last occurrence of the cron (most recent start)
                now_tz = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
                previous_fires = cron_trigger.get_previous_fire_time(now_tz)

                if previous_fires:
                    window_start = previous_fires
                    window_end = window_start + timedelta(minutes=window.duration_minutes)
                    if window_start <= now_tz <= window_end:
                        logger.info(
                            f"Schedule {schedule_id} blocked by maintenance window {window.id}"
                        )
                        return

            # Update last_run_at and call on_fire
            schedule.last_run_at = now
            session.add(schedule)
            await session.commit()

            await self._on_fire(schedule)
