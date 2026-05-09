"""Advisories API: endpoints for advisory management and host advisory tracking."""

from __future__ import annotations

import base64
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Any

from sqlalchemy import desc, select

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.models.advisory import Advisory, AffectedPackage
from server.app.models.host_advisory import HostAdvisory

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/advisories", tags=["advisories"])


# Pydantic models
class AffectedPackageOut(BaseModel):
    """Advisory affected package."""

    ecosystem: str
    package: str
    introduced: str | None = None
    fixed: str | None = None
    range_kind: str = "SEMVER"


class AdvisoryOut(BaseModel):
    """Advisory response model."""

    id: str
    severity: str
    summary: str
    description_md: str | None = None
    kev: bool = False
    epss: float | None = None
    modified: datetime | None = None
    affected_packages: list[AffectedPackageOut] = Field(default_factory=list)


class AdvisoryListResponse(BaseModel):
    """Response wrapper for advisory list."""

    advisories: list[AdvisoryOut]
    next_cursor: str | None = None


class SuppressRequest(BaseModel):
    """Request to suppress a host advisory."""

    reason: str
    expires_at: datetime


class PostureSummaryOut(BaseModel):
    """Fleet posture summary."""

    totals: dict[str, int]
    kev_count: int
    stale_update_hosts: int = 0
    feed_sources: list = Field(default_factory=list)


class FleetAdvisoryRow(BaseModel):
    """Per-advisory rollup across the whole fleet."""

    id: str
    severity: str
    summary: str
    kev: bool
    epss: float | None
    affected_hosts: int
    open_count: int
    suppressed_count: int
    fixed_count: int


class FleetAdvisoryRollupResponse(BaseModel):
    items: list[FleetAdvisoryRow]
    total: int
    # Deduped CVE counts per severity across the full filtered result set
    # (independent of page offset/limit). Lets the UI render accurate stat
    # pills even when paginating.
    severity_counts: dict[str, int] = {}
    kev_count: int = 0


class AdvisoryHostRow(BaseModel):
    host_id: str
    hostname: str
    status: str  # open | suppressed | fixed
    package: str | None = None
    installed_version: str | None = None


class AdvisoryHostsResponse(BaseModel):
    items: list[AdvisoryHostRow]


def _catalog_sm(app_state: Any) -> Any:
    """Return catalog sessionmaker (split-DB) or fall back to fleet sm."""
    return app_state.catalog_sessionmaker or app_state.sessionmaker


def _derive_summary(adv: Any) -> str:
    """Return ``adv.summary`` if non-empty, else first line of description_md.

    Older OSV records (pre-summary-fallback fix) have empty ``summary`` but
    full prose in ``description_md``. Surface a usable line to the UI without
    requiring a full feed resync.
    """
    s = (getattr(adv, "summary", None) or "").strip()
    if s:
        return s
    desc = (getattr(adv, "description_md", None) or "").strip()
    if not desc:
        return ""
    for line in desc.splitlines():
        line = line.strip().lstrip("# ").strip()
        if line:
            return line[:500]
    return ""


@router.get("", response_model=AdvisoryListResponse)
async def list_advisories(
    request: Request,
    severity: str | None = Query(None),
    kev: bool | None = Query(None),
    min_epss: float | None = Query(None),
    package: str | None = Query(None, description="Affected package name substring"),
    q: str | None = Query(None, description="Match on advisory id/summary"),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(admin_required),
) -> AdvisoryListResponse:
    """List advisories with optional filtering and offset pagination.

    Reads from the catalog DB (split file on SQLite, same DB on Postgres).
    """
    app_state = get_app_state(request)
    async with _catalog_sm(app_state)() as session:
        stmt = select(Advisory)

        if severity:
            stmt = stmt.where(Advisory.severity == severity)
        if kev is not None:
            stmt = stmt.where(Advisory.kev == kev)
        if min_epss is not None:
            stmt = stmt.where(Advisory.epss >= min_epss)
        if q:
            like = f"%{q}%"
            stmt = stmt.where((Advisory.id.ilike(like)) | (Advisory.summary.ilike(like)))
        if package:
            pkg_like = f"%{package}%"
            stmt = stmt.where(
                Advisory.id.in_(
                    select(AffectedPackage.advisory_id).where(
                        AffectedPackage.package.ilike(pkg_like)
                    )
                )
            )

        # Simple offset cursor (base64-encoded int) — robust enough for an
        # admin browser; replace with keyset later if it grows.
        offset = 0
        if cursor:
            try:
                offset = int(base64.b64decode(cursor).decode())
            except Exception:
                offset = 0

        stmt = stmt.order_by(
            desc(Advisory.kev),
            desc(Advisory.epss),
            desc(Advisory.modified),
            Advisory.id,
        ).offset(offset).limit(limit + 1)

        advisories_list = list((await session.scalars(stmt)).all())
        next_cursor: str | None = None
        if len(advisories_list) > limit:
            advisories_list = advisories_list[:limit]
            next_cursor = base64.b64encode(str(offset + limit).encode()).decode()

        # Fetch affected packages in one IN query, group locally
        adv_ids = [a.id for a in advisories_list]
        pkg_rows: list[AffectedPackage] = []
        if adv_ids:
            pkg_rows = list(
                (
                    await session.scalars(
                        select(AffectedPackage).where(
                            AffectedPackage.advisory_id.in_(adv_ids)
                        )
                    )
                ).all()
            )
        by_adv: dict[str, list[AffectedPackage]] = {}
        for p in pkg_rows:
            by_adv.setdefault(p.advisory_id, []).append(p)

        result = [
            AdvisoryOut(
                id=adv.id,
                severity=adv.severity,
                summary=_derive_summary(adv),
                kev=adv.kev,
                epss=adv.epss,
                modified=adv.modified,
                affected_packages=[
                    AffectedPackageOut(
                        ecosystem=p.ecosystem,
                        package=p.package,
                        introduced=p.introduced,
                        fixed=p.fixed,
                        range_kind=p.range_kind,
                    )
                    for p in by_adv.get(adv.id, [])
                ],
            )
            for adv in advisories_list
        ]

    return AdvisoryListResponse(advisories=result, next_cursor=next_cursor)


@router.get("/fleet/rollup", response_model=FleetAdvisoryRollupResponse)
async def fleet_advisory_rollup(
    request: Request,
    severity: str | None = Query(None),
    kev: bool | None = Query(None),
    host_id: str | None = Query(None, description="Restrict to a single host"),
    package: str | None = Query(None, description="Match host_advisory.package substring"),
    q: str | None = Query(None, description="Match advisory id or summary"),
    status: str = Query("open"),
    sort: str = Query("affected", pattern="^(affected|severity|epss|id)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(admin_required),
) -> FleetAdvisoryRollupResponse:
    """Aggregate ``host_advisory`` rows across the fleet, joined with the
    catalog DB.

    Cross-engine: query host_advisories from fleet, advisory metadata from
    catalog, then merge in Python so the same path works on SQLite split
    files and unified Postgres.
    """
    app_state = get_app_state(request)

    # Step 1: pull matching host_advisories from the fleet DB.
    async with app_state.sessionmaker() as session:
        ha_stmt = select(HostAdvisory)
        if host_id:
            ha_stmt = ha_stmt.where(HostAdvisory.host_id == host_id)
        if package:
            ha_stmt = ha_stmt.where(HostAdvisory.package.ilike(f"%{package}%"))
        if status and status != "all":
            ha_stmt = ha_stmt.where(HostAdvisory.status == status)
        ha_rows = list((await session.execute(ha_stmt)).scalars().all())

    if not ha_rows:
        return FleetAdvisoryRollupResponse(items=[], total=0, severity_counts={}, kev_count=0)

    advisory_ids = list({r.advisory_id for r in ha_rows})

    # Step 2: pull advisory metadata from catalog DB.
    async with _catalog_sm(app_state)() as cat_session:
        adv_stmt = select(Advisory).where(Advisory.id.in_(advisory_ids))
        if severity:
            adv_stmt = adv_stmt.where(Advisory.severity == severity)
        if kev is not None:
            adv_stmt = adv_stmt.where(Advisory.kev == kev)
        if q:
            like = f"%{q}%"
            adv_stmt = adv_stmt.where(
                (Advisory.id.ilike(like)) | (Advisory.summary.ilike(like))
            )
        adv_rows = list((await cat_session.execute(adv_stmt)).scalars().all())

    by_id = {a.id: a for a in adv_rows}

    # Step 3: rollup per advisory_id.
    rollup: dict[str, FleetAdvisoryRow] = {}
    for r in ha_rows:
        adv = by_id.get(r.advisory_id)
        if adv is None:
            continue  # advisory filtered out by severity/kev/search
        cur = rollup.get(adv.id)
        if cur is None:
            rollup[adv.id] = FleetAdvisoryRow(
                id=adv.id,
                severity=adv.severity or "unknown",
                summary=_derive_summary(adv),
                kev=bool(adv.kev),
                epss=adv.epss,
                affected_hosts=1,
                open_count=1 if r.status == "open" else 0,
                suppressed_count=1 if r.status == "suppressed" else 0,
                fixed_count=1 if r.status == "fixed" else 0,
            )
            cur = rollup[adv.id]
        else:
            cur.affected_hosts += 1
            if r.status == "open":
                cur.open_count += 1
            elif r.status == "suppressed":
                cur.suppressed_count += 1
            elif r.status == "fixed":
                cur.fixed_count += 1

    # We counted host_advisory rows above; affected_hosts is unique-host count.
    # Recompute unique-host counts cleanly.
    by_adv_hosts: dict[str, set[str]] = {}
    for r in ha_rows:
        if r.advisory_id in rollup:
            by_adv_hosts.setdefault(r.advisory_id, set()).add(r.host_id)
    for aid, row in rollup.items():
        row.affected_hosts = len(by_adv_hosts.get(aid, set()))

    sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}
    items = list(rollup.values())
    if sort == "affected":
        items.sort(key=lambda x: (-x.affected_hosts, -sev_rank.get(x.severity, 0), x.id))
    elif sort == "severity":
        items.sort(key=lambda x: (-sev_rank.get(x.severity, 0), -x.affected_hosts, x.id))
    elif sort == "epss":
        items.sort(key=lambda x: (-(x.epss or 0.0), -x.affected_hosts, x.id))
    else:
        items.sort(key=lambda x: x.id)

    total = len(items)
    severity_counts: dict[str, int] = {}
    kev_count = 0
    for row in items:
        severity_counts[row.severity] = severity_counts.get(row.severity, 0) + 1
        if row.kev:
            kev_count += 1
    items = items[offset : offset + limit]
    return FleetAdvisoryRollupResponse(
        items=items,
        total=total,
        severity_counts=severity_counts,
        kev_count=kev_count,
    )


@router.get("/{advisory_id}/hosts", response_model=AdvisoryHostsResponse)
async def list_advisory_hosts(
    request: Request,
    advisory_id: str,
    status: str = Query("open", description="Filter by host_advisory.status; 'all' to skip"),
    _: str = Depends(admin_required),
) -> AdvisoryHostsResponse:
    """Return hosts affected by a given advisory. Joins host_advisory rows
    (fleet DB) with host records to surface hostnames in the UI."""
    from server.app.models.host import Host  # local import: avoid cycles

    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        stmt = select(HostAdvisory).where(HostAdvisory.advisory_id == advisory_id)
        if status and status != "all":
            stmt = stmt.where(HostAdvisory.status == status)
        ha_rows = list((await session.execute(stmt)).scalars().all())

        if not ha_rows:
            return AdvisoryHostsResponse(items=[])

        host_ids = list({r.host_id for r in ha_rows})
        host_rows = list(
            (await session.execute(select(Host).where(Host.id.in_(host_ids)))).scalars().all()
        )

    by_host = {h.id: h for h in host_rows}
    items = []
    for r in ha_rows:
        h = by_host.get(r.host_id)
        items.append(
            AdvisoryHostRow(
                host_id=r.host_id,
                hostname=(h.hostname if h else r.host_id),
                status=r.status,
                package=getattr(r, "package", None),
                installed_version=getattr(r, "installed_version", None),
            )
        )
    items.sort(key=lambda x: x.hostname.lower())
    return AdvisoryHostsResponse(items=items)


@router.get("/{advisory_id}", response_model=AdvisoryOut)
async def get_advisory(
    request: Request,
    advisory_id: str,
    _: str = Depends(admin_required),
) -> AdvisoryOut:
    """Get a single advisory by ID (catalog DB)."""
    app_state = get_app_state(request)
    async with _catalog_sm(app_state)() as session:
        adv = await session.get(Advisory, advisory_id)
        if not adv:
            raise HTTPException(status_code=404, detail="Advisory not found")

        packages_result = await session.scalars(
            select(AffectedPackage).where(AffectedPackage.advisory_id == advisory_id)
        )
        packages = packages_result.all()

        return AdvisoryOut(
            id=adv.id,
            severity=adv.severity,
            summary=_derive_summary(adv),
            description_md=getattr(adv, "description_md", None),
            kev=adv.kev,
            epss=adv.epss,
            modified=adv.modified,
            affected_packages=[
                AffectedPackageOut(
                    ecosystem=p.ecosystem,
                    package=p.package,
                    introduced=p.introduced,
                    fixed=p.fixed,
                    range_kind=p.range_kind,
                )
                for p in packages
            ],
        )
