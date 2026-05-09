"""Posture Risk HTTP endpoints (Task 12 — GET /v1/hosts/{id}/risk)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state

router = APIRouter(tags=["posture", "risk"])


class PillarOut(BaseModel):
    name: str
    label: str
    score: float
    confidence: float
    weight: float
    drivers: list[dict]
    coverage_notes: list[str]


class HostRiskOut(BaseModel):
    host_id: str
    score: int | None
    level: str
    confidence: float
    pillars: list[PillarOut]
    floor_triggered: bool
    computed_at: datetime
    inputs_hash: str


@router.get("/v1/hosts/{host_id}/risk", response_model=HostRiskOut)
async def get_host_risk(
    request: Request,
    host_id: str,
    _: str = Depends(admin_required),
) -> HostRiskOut:
    """Return the cached multi-pillar risk snapshot for a host.

    Lazy-computes on first read if no row exists yet. Stale snapshots
    (>1h) trigger a background refresh but the cached value is served
    immediately to keep the response fast.
    """
    state = get_app_state(request)
    from server.app.models.host import Host
    from server.app.models.host_risk import HostRisk

    async with state.sessionmaker() as session:
        host = await session.get(Host, host_id)
        if host is None:
            raise HTTPException(status_code=404, detail="host_not_found")
        row = await session.get(HostRisk, host_id)

    if row is None and state.risk_recomputer is not None:
        await state.risk_recomputer.recompute(host_id, trigger_reason="api_first_read")
        async with state.sessionmaker() as session:
            row = await session.get(HostRisk, host_id)

    if row is None:
        raise HTTPException(status_code=503, detail="risk_unavailable")

    computed_at = row.computed_at
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)

    if (datetime.now(timezone.utc) - computed_at) > timedelta(hours=1):
        if state.risk_recomputer is not None:
            asyncio.create_task(
                state.risk_recomputer.request(host_id, trigger_reason="stale")
            )

    pillars_dict = row.pillars or {}
    reg = state.risk_registry
    label_lookup: dict[str, str] = {}
    if reg is not None:
        # ScorerRegistry exposes scorers via private dict; use config() for labels.
        for s in reg.config().scorers:
            label_lookup[s["name"]] = s["label"]

    pillars = [
        PillarOut(
            name=name,
            label=label_lookup.get(name, name),
            score=p.get("score", 0),
            confidence=p.get("confidence", 0),
            weight=p.get("weight", 0),
            drivers=p.get("drivers", []),
            coverage_notes=p.get("coverage_notes", []),
        )
        for name, p in pillars_dict.items()
    ]

    return HostRiskOut(
        host_id=host_id,
        score=row.score,
        level=row.level,
        confidence=row.confidence,
        pillars=pillars,
        floor_triggered=row.floor_triggered,
        computed_at=row.computed_at,
        inputs_hash=row.inputs_hash,
    )


class RiskConfigOut(BaseModel):
    weights: dict[str, float]
    scorers: list[dict]


class RiskConfigPatch(BaseModel):
    weights: dict[str, float] | None = None
    enabled: dict[str, bool] | None = None


@router.get("/v1/posture/risk/config", response_model=RiskConfigOut)
async def get_risk_config(request: Request, _: str = Depends(admin_required)) -> RiskConfigOut:
    state = get_app_state(request)
    if state.risk_registry is None:
        raise HTTPException(status_code=503, detail="risk_registry_unavailable")
    cfg = state.risk_registry.config()
    return RiskConfigOut(weights=cfg.weights, scorers=cfg.scorers)


@router.patch("/v1/posture/risk/config", response_model=RiskConfigOut)
async def patch_risk_config(
    request: Request,
    body: RiskConfigPatch,
    _: str = Depends(admin_required),
) -> RiskConfigOut:
    state = get_app_state(request)
    if state.risk_registry is None:
        raise HTTPException(status_code=503, detail="risk_registry_unavailable")
    try:
        state.risk_registry.apply_overrides(
            weights=body.weights or {},
            enabled=body.enabled or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cfg = state.risk_registry.config()
    return RiskConfigOut(weights=cfg.weights, scorers=cfg.scorers)


@router.get("/v1/posture/risk/scorers")
async def list_scorers(request: Request, _: str = Depends(admin_required)) -> dict:
    state = get_app_state(request)
    if state.risk_registry is None:
        raise HTTPException(status_code=503, detail="risk_registry_unavailable")
    return {"scorers": state.risk_registry.config().scorers}


class SummaryRow(BaseModel):
    host_id: str
    score: int | None
    level: str
    confidence: float


class SummaryResponse(BaseModel):
    items: list[SummaryRow]


@router.get("/v1/posture/risk/summary", response_model=SummaryResponse)
async def risk_summary(
    request: Request,
    level: str | None = None,
    confidence_min: float = 0.0,
    _: str = Depends(admin_required),
) -> SummaryResponse:
    state = get_app_state(request)
    from sqlalchemy import select

    from server.app.models.host_risk import HostRisk

    async with state.sessionmaker() as session:
        stmt = select(HostRisk)
        if level:
            stmt = stmt.where(HostRisk.level == level)
        rows = list((await session.execute(stmt)).scalars().all())
    return SummaryResponse(
        items=[
            SummaryRow(
                host_id=r.host_id,
                score=r.score,
                level=r.level,
                confidence=r.confidence,
            )
            for r in rows
            if r.confidence >= confidence_min
        ]
    )


@router.post("/v1/hosts/{host_id}/risk/recompute", status_code=202)
async def recompute_host_risk(
    request: Request,
    host_id: str,
    _: str = Depends(admin_required),
) -> dict:
    state = get_app_state(request)
    if state.risk_recomputer is None:
        raise HTTPException(status_code=503, detail="recomputer_unavailable")
    asyncio.create_task(
        state.risk_recomputer.recompute(host_id, trigger_reason="manual", force=True)
    )
    return {"status": "queued"}
