"""Posture API: GET /v1/posture returns ranked security findings."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.posture import ALL_FINDINGS, SEVERITY_ORDER
from server.app.posture.model import Finding
from server.app.settings.config import load_settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/posture", tags=["posture"])


class FindingOut(BaseModel):
    id: str
    severity: str
    title: str
    summary: str
    fix_action_url: str | None = Field(default=None)
    docs_url: str | None = Field(default=None)


class PostureResponse(BaseModel):
    findings: list[FindingOut]


@router.get("", response_model=PostureResponse)
async def get_posture(
    request: Request,
    _: str = Depends(admin_required),
) -> PostureResponse:
    """Run all posture finding functions in parallel and return ranked list."""
    app_state = get_app_state(request)
    settings = load_settings()

    ctx: dict[str, Any] = {
        "broker": app_state.secrets_broker,
        "settings": settings,
    }

    results = await asyncio.gather(
        *(fn(app_state.sessionmaker, **ctx) for fn in ALL_FINDINGS),
        return_exceptions=True,
    )

    findings: list[Finding] = []
    for r in results:
        if isinstance(r, Finding):
            findings.append(r)
        elif isinstance(r, Exception):
            log.warning("posture_finding_failed", exc=str(r))

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))

    return PostureResponse(
        findings=[
            FindingOut(
                id=f.id,
                severity=f.severity,
                title=f.title,
                summary=f.summary,
                fix_action_url=f.fix_action_url,
                docs_url=f.docs_url,
            )
            for f in findings
        ]
    )
