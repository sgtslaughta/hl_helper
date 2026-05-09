"""Advisory worker.

Single asyncio task that owns:
  * the catalog sessionmaker (sole writer to advisory tables — no SQLite
    contention with API/heartbeat),
  * a bounded feed-sync queue (admin trigger + interval ticks),
  * a bounded match queue (one entry per host_id, deduped via a pending set),
  * timer ticks per feed.

API/heartbeat code calls ``worker.enqueue_*()`` which is a non-blocking put;
on full queue we drop with a warn — bounded backpressure, no cascading
slowdowns. The worker drains queues serially per kind so writers don't fight
each other.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.advisory.feeds.epss import EPSSScoreFeed
from server.app.advisory.feeds.kev import KEVScoreFeed
from server.app.advisory.matcher import _candidate_ecosystems, match_host
from server.app.advisory.store import apply_scores
from server.app.models import FeedStatus, HostPackage
from server.app.models.host import Host
from server.app.settings.config import DEFAULT_LANGUAGE_ECOSYSTEMS, FleetSettings

log = structlog.get_logger(__name__)

FEED_NAMES: tuple[str, ...] = ("osv", "epss", "kev")


class AdvisoryWorker:
    """Owns advisory feed sync + per-host match dispatch.

    Lifecycle: ``await run()`` runs forever until cancelled. Bound to an
    asyncio task in lifespan and cancelled on shutdown.
    """

    def __init__(
        self,
        catalog_sm: async_sessionmaker[AsyncSession],
        fleet_sm: async_sessionmaker[AsyncSession],
        settings: FleetSettings,
        *,
        feed_sync_queue_maxsize: int = 4,
        match_queue_maxsize: int = 32,
        event_bus: object | None = None,
        risk_recomputer: object | None = None,
    ) -> None:
        self._catalog_sm = catalog_sm
        self._fleet_sm = fleet_sm
        self._settings = settings
        self._event_bus = event_bus
        self._risk_recomputer = risk_recomputer

        self.feed_sync_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(
            maxsize=feed_sync_queue_maxsize
        )
        self.match_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=match_queue_maxsize)

        # Pending-match dedup. Lock guards both the queue put and the set
        # mutation so we never enqueue the same host twice while one is
        # already pending or running.
        self._pending_matches: set[str] = set()
        self._match_lock = asyncio.Lock()

        # In-progress flag per feed, surfaced via the status endpoint.
        self.in_progress: dict[str, bool] = {f: False for f in FEED_NAMES}

    # ---- Public enqueue API ----

    def enqueue_feed_sync(self, feed_name: str, *, trigger: str = "manual") -> bool:
        """Enqueue a feed sync. Returns False if the queue is full."""
        if feed_name not in FEED_NAMES:
            raise ValueError(f"unknown feed: {feed_name}")
        try:
            self.feed_sync_queue.put_nowait((feed_name, trigger))
            return True
        except asyncio.QueueFull:
            log.warning("advisory_worker.feed_queue_full", feed=feed_name)
            return False

    async def enqueue_match(self, host_id: str) -> bool:
        """Enqueue a host re-match. Deduplicates pending requests for the same host."""
        async with self._match_lock:
            if host_id in self._pending_matches:
                return False
            try:
                self.match_queue.put_nowait(host_id)
            except asyncio.QueueFull:
                log.warning("advisory_worker.match_queue_full", host_id=host_id)
                return False
            self._pending_matches.add(host_id)
            return True

    # ---- Worker entrypoint ----

    async def run(self) -> None:
        """Drive the three internal coroutines until cancelled."""
        sync_task = asyncio.create_task(self._sync_loop(), name="advisory_sync_loop")
        match_task = asyncio.create_task(self._match_loop(), name="advisory_match_loop")
        tick_task = asyncio.create_task(self._tick_loop(), name="advisory_tick_loop")

        try:
            if self._settings.advisory_sync_on_startup:
                for f in FEED_NAMES:
                    self.enqueue_feed_sync(f, trigger="startup")
            await asyncio.gather(sync_task, match_task, tick_task)
        except asyncio.CancelledError:
            for t in (sync_task, match_task, tick_task):
                t.cancel()
            for t in (sync_task, match_task, tick_task):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            raise

    # ---- Internal loops ----

    async def _sync_loop(self) -> None:
        while True:
            feed_name, trigger = await self.feed_sync_queue.get()
            try:
                await self._run_feed(feed_name, trigger)
            except Exception:
                log.exception("advisory_worker.sync_failed", feed=feed_name)
            finally:
                self.feed_sync_queue.task_done()

    async def _match_loop(self) -> None:
        while True:
            host_id = await self.match_queue.get()
            ok = False
            try:
                count = await match_host(self._fleet_sm, host_id, catalog_sm=self._catalog_sm)
                ok = True
                log.info("advisory_worker.match_done", host_id=host_id, count=count)
            except Exception:
                log.exception("advisory_worker.match_failed", host_id=host_id)
            finally:
                async with self._match_lock:
                    self._pending_matches.discard(host_id)
                self.match_queue.task_done()
            try:
                await self._close_rescan_tasks(host_id, succeeded=ok)
            except Exception:
                log.warning("advisory_worker.rescan_close_failed", host_id=host_id, exc_info=True)
            if ok and self._risk_recomputer is not None:
                try:
                    await self._risk_recomputer.request(
                        host_id, trigger_reason="advisory_match"
                    )
                except Exception:
                    log.warning(
                        "advisory_worker.risk_recompute_request_failed",
                        host_id=host_id,
                        exc_info=True,
                    )

    async def _close_rescan_tasks(self, host_id: str, *, succeeded: bool) -> None:
        """Mark RUNNING rescan/resurvey Task rows for this host as terminal.

        Without this hook the UI shows manual rescan tasks "running" forever,
        because the agent never sends a result envelope back for inventory
        ingest — the work is implicit on the next inventory message + match.
        """
        from datetime import datetime, timezone as tz
        from sqlalchemy import select, or_

        from server.app.models.task import Task, TaskStatus
        from server.app.models.task_run import TaskRun, TaskRunStatus

        now = datetime.now(tz.utc)
        target_status = TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED
        run_status = TaskRunStatus.SUCCEEDED if succeeded else TaskRunStatus.FAILED

        async with self._fleet_sm() as session:
            # Pull all RUNNING rescan/resurvey tasks for this host. payload
            # is JSON; SQLAlchemy doesn't have a portable JSON contains for
            # SQLite + Postgres, so we fetch then filter in Python.
            stmt = select(Task).where(Task.status == TaskStatus.RUNNING)
            tasks = list((await session.execute(stmt)).scalars().all())
            tasks = [
                t for t in tasks
                if isinstance(t.payload, dict)
                and t.payload.get("host_id") == host_id
                and t.payload.get("action") in ("rescan", "resurvey")
            ]
            if not tasks:
                return

            for t in tasks:
                t.status = target_status

            stmt_runs = select(TaskRun).where(
                TaskRun.task_id.in_([t.id for t in tasks]),
                or_(TaskRun.status == TaskRunStatus.RUNNING, TaskRun.status == TaskRunStatus.PENDING),
            )
            runs = list((await session.execute(stmt_runs)).scalars().all())
            for r in runs:
                r.status = run_status
                r.finished_at = now

            await session.commit()
            log.info(
                "advisory_worker.rescan_tasks_closed",
                host_id=host_id,
                tasks=len(tasks),
                runs=len(runs),
                status=target_status.value,
            )

    async def _tick_loop(self) -> None:
        """Periodic timer per feed. First fire happens after ``interval`` seconds.

        We don't fire-and-forget every loop iteration; we use individual sleep
        timers so feed cadences stay independent.
        """
        if not self._settings.advisory_enabled:
            log.info("advisory_worker.disabled_by_settings")
            await asyncio.Event().wait()  # park forever
            return

        await asyncio.gather(
            self._tick_feed("osv"),
            self._tick_feed("epss"),
            self._tick_feed("kev"),
        )

    async def _tick_feed(self, feed_name: str) -> None:
        interval = self._settings.advisory_sync_intervals.get(feed_name, 86400)
        while True:
            await asyncio.sleep(interval)
            self.enqueue_feed_sync(feed_name, trigger="tick")

    # ---- Feed dispatch ----

    async def _run_feed(self, feed_name: str, trigger: str) -> None:
        self.in_progress[feed_name] = True
        started = datetime.now(timezone.utc)
        log.info("advisory_worker.feed_start", feed=feed_name, trigger=trigger)
        await self._emit_ticker_sync(feed_name, phase="started")
        last_count = 0
        last_error: str | None = None

        try:
            if feed_name == "osv":
                allowlist = await self._resolve_ecosystems()
                # Lazy import: avoids cost when feed is disabled / never run.
                from server.app.advisory.feeds.osv_stream import osv_sync_stream

                inserted, updated, errors = await osv_sync_stream(
                    self._catalog_sm,
                    ecosystem_allowlist=allowlist,
                )
                last_count = inserted + updated
                if errors:
                    last_error = f"{len(errors)} entries failed; first: {errors[0][:200]}"
                log.info(
                    "advisory_worker.osv_done",
                    inserted=inserted,
                    updated=updated,
                    errors=len(errors),
                    ecosystems=len(allowlist),
                )

            elif feed_name == "epss":
                feed = EPSSScoreFeed()
                scores = await feed.sync()
                last_count = await apply_scores(self._catalog_sm, scores, kind="epss")

            elif feed_name == "kev":
                feed = KEVScoreFeed()
                scores = await feed.sync()
                last_count = await apply_scores(self._catalog_sm, scores, kind="kev")

        except Exception as e:
            last_error = str(e)[:1000]
            log.exception("advisory_worker.feed_error", feed=feed_name)

        finally:
            self.in_progress[feed_name] = False
            await self._record_status(feed_name, started, last_count, last_error)
            if last_error is not None:
                await self._emit_ticker_sync(feed_name, phase="error", error=last_error)
            else:
                await self._emit_ticker_sync(feed_name, phase="completed", count=last_count)

    async def _emit_ticker_sync(
        self,
        feed_name: str,
        *,
        phase: str,
        count: int | None = None,
        error: str | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        try:
            from server.app.events.ticker import (
                format_advisory_sync,
                publish_ticker,
            )

            fmt = format_advisory_sync(
                feed=feed_name,
                phase=phase,  # type: ignore[arg-type]
                count=count,
                error=error,
            )
            await publish_ticker(self._event_bus, **fmt)  # type: ignore[arg-type]
        except Exception:
            log.warning("advisory_worker.ticker_emit_failed", feed=feed_name, exc_info=True)

    # ---- Ecosystem resolver ----

    async def _resolve_ecosystems(self) -> list[str]:
        """Return the list of OSV ecosystems to sync.

        - Explicit list in settings: returned as-is.
        - "auto": derive from currently enrolled hosts' (ecosystem, os_version)
          via _candidate_ecosystems, then optionally union with language defaults.
        - With zero hosts enrolled and language defaults on, returns just languages.
        """
        configured = self._settings.advisory_ecosystems
        if isinstance(configured, list):
            return list(dict.fromkeys(configured))  # dedup preserve order

        # auto mode
        derived: set[str] = set()
        async with self._fleet_sm() as session:
            stmt = select(Host.id, Host.survey).where(Host.status != "revoked")
            hosts = list((await session.execute(stmt)).all())

            stmt_pkgs = select(HostPackage.ecosystem).distinct()
            host_ecos = list((await session.execute(stmt_pkgs)).scalars().all())

        # For each host, look at its os_version and combine with each known
        # raw ecosystem. _candidate_ecosystems handles unknown ecos by passing
        # them through unchanged (good for PyPI/npm/etc).
        for _hid, survey in hosts:
            os_version = None
            if isinstance(survey, dict):
                os_version = survey.get("os_version")
            for raw in host_ecos or [""]:
                for cand in _candidate_ecosystems(raw, os_version):
                    if cand:
                        derived.add(cand)

        if self._settings.advisory_always_include_languages:
            derived.update(DEFAULT_LANGUAGE_ECOSYSTEMS)

        # If no hosts and no languages, fall back to language list anyway —
        # otherwise OSV would skip every record.
        if not derived:
            derived.update(DEFAULT_LANGUAGE_ECOSYSTEMS)

        return sorted(derived)

    # ---- Status persistence ----

    async def _record_status(
        self,
        feed_name: str,
        started_at: datetime,
        last_count: int,
        last_error: str | None,
    ) -> None:
        interval = self._settings.advisory_sync_intervals.get(feed_name, 86400)
        next_at = started_at + timedelta(seconds=interval)
        try:
            async with self._catalog_sm() as session:
                # Upsert. SQLite + Postgres both expose ON CONFLICT for the
                # primary key column; sqlite_insert works on Postgres too via
                # the dialect-neutral excluded reference if we keep keys lower.
                stmt = sqlite_insert(FeedStatus).values(
                    feed_name=feed_name,
                    last_sync_at=started_at,
                    last_count=last_count,
                    last_error=last_error,
                    next_scheduled_at=next_at,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[FeedStatus.feed_name],
                    set_={
                        "last_sync_at": started_at,
                        "last_count": last_count,
                        "last_error": last_error,
                        "next_scheduled_at": next_at,
                    },
                )
                await session.execute(stmt)
                await session.commit()
        except Exception:
            log.exception("advisory_worker.status_write_failed", feed=feed_name)

    async def get_status(self) -> list[dict[str, Any]]:
        """Return current per-feed status snapshot, joined with worker in-progress flags."""
        async with self._catalog_sm() as session:
            rows = list((await session.execute(select(FeedStatus))).scalars().all())
        by_name = {r.feed_name: r for r in rows}
        out: list[dict[str, Any]] = []
        for name in FEED_NAMES:
            row = by_name.get(name)
            out.append({
                "feed": name,
                "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
                "last_count": row.last_count if row else 0,
                "last_error": row.last_error if row else None,
                "next_scheduled_at": (
                    row.next_scheduled_at.isoformat() if row and row.next_scheduled_at else None
                ),
                "in_progress": self.in_progress.get(name, False),
            })
        return out
