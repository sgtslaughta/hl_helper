"""Posture inspector — cross-component aggregator.

@brief Runs all registered finding functions in parallel, persists results
       to the posture store, and expires stale suppressions.  Designed to
       be called periodically (default 300 s) by the scheduler or on-demand
       from the API.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.posture import ALL_FINDINGS
from server.app.posture.model import Finding
from server.app.posture.store import expire_suppressions, upsert_finding
from server.app.settings.config import FleetSettings, load_settings

log = structlog.get_logger(__name__)

DEFAULT_INTERVAL_S = 300


async def run_inspection(
    sm: async_sessionmaker[AsyncSession],
    *,
    broker: Any | None = None,
    settings: FleetSettings | None = None,
) -> list[Finding]:
    """@brief Execute all posture finding functions and persist results.

    Finding functions that raise or return ``None`` are silently skipped.
    After collection, stale suppressions are expired.

    @param sm       Async sessionmaker for database access.
    @param broker   Optional secrets broker passed to finding functions.
    @param settings Optional fleet settings (loaded if not provided).
    @return List of active (non-None) findings produced by this run.
    """
    if settings is None:
        settings = load_settings()

    ctx: dict[str, Any] = {"broker": broker, "settings": settings}

    results = await asyncio.gather(
        *(fn(sm, **ctx) for fn in ALL_FINDINGS),
        return_exceptions=True,
    )

    findings: list[Finding] = []
    for r in results:
        if isinstance(r, Finding):
            findings.append(r)
        elif isinstance(r, Exception):
            log.warning("posture_inspector_finding_failed", exc=str(r))

    for f in findings:
        try:
            await upsert_finding(sm, f)
        except Exception:
            log.warning("posture_inspector_upsert_failed", finding_id=f.id, exc_info=True)

    try:
        expired = await expire_suppressions(sm)
        if expired:
            log.info("posture_inspector_expired_suppressions", count=expired)
    except Exception:
        log.warning("posture_inspector_expire_failed", exc_info=True)

    return findings
