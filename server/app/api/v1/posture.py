"""Posture API: findings list, suppress, and unsuppress endpoints.

@brief Provides GET /v1/posture for ranked findings (backed by the
persistent store), and POST actions to suppress or unsuppress
individual findings.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.models.advisory import Advisory
from server.app.models.host_advisory import HostAdvisory
from server.app.posture.inspector import run_inspection
from server.app.posture.model import PostureFindingRow
from server.app.posture.store import list_findings, suppress_finding, unsuppress_finding
from server.app.settings.config import load_settings
from sqlalchemy import func, select, and_

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/posture", tags=["posture"])


class FindingOut(BaseModel):
    """@brief Serialized posture finding for API responses."""

    id: str
    severity: str
    title: str
    summary: str
    fix_action_url: str | None = Field(default=None)
    docs_url: str | None = Field(default=None)
    rule: str = ""
    subject_kind: str = "global"
    subject_id: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    suppressed_until: datetime | None = None
    suppressed_by: str | None = None
    suppressed_reason: str | None = None


class PostureResponse(BaseModel):
    """@brief Wrapper for the posture findings list."""

    findings: list[FindingOut]


class SuppressRequest(BaseModel):
    """@brief Request body for suppressing a finding."""

    finding_id: str
    reason: str
    expires_at: datetime


class UnsuppressRequest(BaseModel):
    """@brief Request body for unsuppressing a finding."""

    finding_id: str


class PostureSummaryOut(BaseModel):
    """@brief Fleet posture summary."""

    totals: dict[str, int]
    kev_count: int
    stale_update_hosts: int = 0
    feed_sources: list = Field(default_factory=list)


def _row_to_out(row: PostureFindingRow) -> FindingOut:
    """@brief Convert a PostureFindingRow ORM object to a FindingOut response.

    @param row Persisted posture finding row.
    @return Serializable Pydantic model.
    """
    return FindingOut(
        id=row.id,
        severity=row.severity,
        title=row.title,
        summary=row.summary,
        fix_action_url=row.fix_action_url,
        docs_url=row.docs_url,
        rule=row.rule,
        subject_kind=row.subject_kind,
        subject_id=row.subject_id,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        suppressed_until=row.suppressed_until,
        suppressed_by=row.suppressed_by,
        suppressed_reason=row.suppressed_reason,
    )


@router.get("", response_model=PostureResponse)
async def get_posture(
    request: Request,
    _: str = Depends(admin_required),
    include_suppressed: bool = Query(default=False),
    subject_kind: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
) -> PostureResponse:
    """@brief Run posture inspection, persist results, return from store.

    Delegates to ``run_inspection`` to execute finding functions and
    persist results, then reads back from the store so suppression
    filters operate on persisted state.

    @param request            The incoming HTTP request.
    @param include_suppressed If True, include suppressed findings.
    @param subject_kind       Filter findings by subject_kind (e.g., 'host').
    @param subject_id         Filter findings by subject_id.
    @return PostureResponse with sorted findings.
    """
    app_state = get_app_state(request)
    settings = load_settings()

    await run_inspection(
        app_state.sessionmaker,
        broker=app_state.secrets_broker,
        settings=settings,
        catalog_sm=app_state.catalog_sessionmaker,
        event_bus=app_state.bus,
        risk_recomputer=getattr(app_state, "risk_recomputer", None),
    )

    suppressed_filter = None if include_suppressed else False
    rows = await list_findings(
        app_state.sessionmaker,
        suppressed=suppressed_filter,
        subject_kind=subject_kind,
        subject_id=subject_id,
    )

    return PostureResponse(findings=[_row_to_out(r) for r in rows])


@router.post("/actions/suppress", response_model=FindingOut)
async def suppress_posture_finding(
    request: Request,
    body: SuppressRequest,
    actor: str = Depends(admin_required),
) -> FindingOut:
    """@brief Suppress a posture finding.

    @param request  The incoming HTTP request.
    @param body     SuppressRequest with finding_id, reason, and expires_at.
    @param actor    Admin actor from auth dependency.
    @return The updated finding.
    @raises HTTPException 404 if finding not found.
    """
    app_state = get_app_state(request)
    row = await suppress_finding(
        app_state.sessionmaker,
        body.finding_id,
        suppressed_by=actor,
        reason=body.reason,
        expires_at=body.expires_at,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _row_to_out(row)


@router.post("/actions/unsuppress", response_model=FindingOut)
async def unsuppress_posture_finding(
    request: Request,
    body: UnsuppressRequest,
    _: str = Depends(admin_required),
) -> FindingOut:
    """@brief Unsuppress a posture finding.

    @param request  The incoming HTTP request.
    @param body     UnsuppressRequest with finding_id.
    @return The updated finding.
    @raises HTTPException 404 if finding not found.
    """
    app_state = get_app_state(request)
    row = await unsuppress_finding(app_state.sessionmaker, body.finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _row_to_out(row)


@router.get("/summary", response_model=PostureSummaryOut)
async def get_posture_summary(
    request: Request,
    _: str = Depends(admin_required),
) -> PostureSummaryOut:
    """@brief Fleet posture summary: severity counts, KEV count, stale hosts.

    @param request The incoming HTTP request.
    @return PostureSummaryOut with aggregated metrics.
    """
    app_state = get_app_state(request)
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    kev_count = 0

    # Step 1: pull every open host_advisory's advisory_id from the fleet DB.
    async with app_state.sessionmaker() as session:
        stmt = select(HostAdvisory.advisory_id).where(HostAdvisory.status == "open")
        adv_ids = list((await session.execute(stmt)).scalars().all())

    if adv_ids:
        # Step 2: look up severity + kev in the catalog DB. Group with a single
        # IN-list query, then count locally — works on SQLite split files and
        # Postgres unified deployments without cross-engine JOINs.
        unique_ids = list(set(adv_ids))
        catalog_sm = app_state.catalog_sessionmaker or app_state.sessionmaker
        async with catalog_sm() as cat_session:
            stmt_adv = select(Advisory.id, Advisory.severity, Advisory.kev).where(
                Advisory.id.in_(unique_ids)
            )
            adv_rows = list((await cat_session.execute(stmt_adv)).all())

        by_id = {row.id: (row.severity, bool(row.kev)) for row in adv_rows}
        for aid in adv_ids:
            sev, kev = by_id.get(aid, ("unknown", False))
            if sev in severity_counts:
                severity_counts[sev] += 1
            if kev:
                kev_count += 1

    return PostureSummaryOut(
        totals=severity_counts,
        kev_count=kev_count,
        stale_update_hosts=0,
        feed_sources=[],
    )
