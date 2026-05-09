"""Periodic background task: detect heartbeat-timed-out hosts and emit ticker events.

A host is considered offline when ``last_seen_at`` is older than
``heartbeat_interval_s * STALE_FACTOR``. Hosts already marked offline (or with
no heartbeat ever) are skipped.

The watcher publishes a ticker event for each transition so the WebUI footer
shows "Host X offline" the next time the timer fires.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.events.bus import Bus
from server.app.events.ticker import format_host_status, publish_ticker
from server.app.models.host import Host

log = logging.getLogger(__name__)

STALE_FACTOR = 3
DEFAULT_TICK_SECONDS = 15.0


async def scan_offline_transitions(
    sm: async_sessionmaker, bus: Bus
) -> list[str]:
    """Single sweep: flip stale healthy hosts to ``offline`` + publish ticker.

    Returns the list of host ids that transitioned this sweep.
    """
    now = datetime.now(timezone.utc)
    flipped: list[tuple[str, str]] = []  # (host_id, hostname)

    async with sm() as session:
        rows = (
            await session.execute(
                select(Host).where(
                    Host.status != "offline",
                    Host.last_seen_at.is_not(None),
                )
            )
        ).scalars().all()

        for host in rows:
            assert host.last_seen_at is not None  # narrowed by where-clause
            cutoff = host.heartbeat_interval_s * STALE_FACTOR
            seen = host.last_seen_at
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            age = (now - seen).total_seconds()
            if age > cutoff:
                host.status = "offline"
                flipped.append((host.id, host.hostname))
        if flipped:
            await session.commit()

    for host_id, hostname in flipped:
        msg = format_host_status(host_id=host_id, hostname=hostname, online=False)
        await publish_ticker(bus, **msg)  # type: ignore[arg-type]

    return [hid for hid, _ in flipped]


async def run_host_status_watcher(
    sm: async_sessionmaker,
    bus: Bus,
    *,
    interval_s: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Long-running task: tick every ``interval_s`` until cancelled."""
    while True:
        try:
            await scan_offline_transitions(sm, bus)
        except Exception:
            log.exception("host_status_watcher.tick_failed")
        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            return
