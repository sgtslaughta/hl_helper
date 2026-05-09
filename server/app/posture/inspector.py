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

from server.app.posture import ALL_FINDINGS, ALL_LIST_FINDINGS
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
    catalog_sm: async_sessionmaker[AsyncSession] | None = None,
    event_bus: Any | None = None,
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

    ctx: dict[str, Any] = {"broker": broker, "settings": settings, "catalog_sm": catalog_sm}

    # Collect single-return findings
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

    # Collect list-return findings
    list_results = await asyncio.gather(
        *(fn(sm, **ctx) for fn in ALL_LIST_FINDINGS),
        return_exceptions=True,
    )

    for r in list_results:
        if isinstance(r, list):
            for f in r:
                if isinstance(f, Finding):
                    findings.append(f)
        elif isinstance(r, Exception):
            log.warning("posture_inspector_list_finding_failed", exc=str(r))

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

    # Ticker: announce scan completion fleet-wide (severity reflects worst finding)
    if event_bus is not None:
        try:
            from server.app.events.ticker import publish_ticker

            sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
            worst = None
            worst_rank = -1
            for f in findings:
                # Finding.severity may be enum-like; coerce to lowercase str
                s = str(getattr(f, "severity", "")).lower().split(".")[-1]
                if s in sev_rank and sev_rank[s] > worst_rank:
                    worst = s
                    worst_rank = sev_rank[s]
            if not findings:
                ticker_sev = "ok"
            elif worst in ("critical",):
                ticker_sev = "error"
            elif worst in ("high", "medium"):
                ticker_sev = "warn"
            else:
                ticker_sev = "info"
            await publish_ticker(
                event_bus,
                type="posture",
                severity=ticker_sev,  # type: ignore[arg-type]
                text=f"Posture scan complete ({len(findings)} findings)",
                meta={"finding_count": len(findings), "max_severity": worst},
            )
        except Exception:
            log.warning("posture_inspector_ticker_emit_failed", exc_info=True)

    return findings
