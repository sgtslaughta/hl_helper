"""Advisories API: stub for security advisories management."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/advisories", tags=["advisories"])
log = structlog.get_logger(__name__)


class AdvisoryOut(BaseModel):
    """Advisory response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Advisory ID")
    severity: str = Field(..., description="Severity level")
    host_id: str = Field(..., description="Affected host ID")


class DismissActionResponse(BaseModel):
    """Response for dismiss action."""

    ok: bool = Field(..., description="Action success indicator")


@router.get("", response_model=list[AdvisoryOut])
async def list_advisories(
    severity: str | None = None,
    host_id: str | None = None,
    actor: str = Depends(admin_required),
) -> list[AdvisoryOut]:
    """List advisories with optional filtering.

    Args:
        severity: Filter by severity level (optional)
        host_id: Filter by host ID (optional)

    Returns:
        Empty list (TODO: fetch from persistence layer)
    """
    log.info("list_advisories", severity=severity, host_id=host_id, actor=actor)
    # TODO: Query advisories from persistence layer with filters
    return []


@router.get("/{advisory_id}", response_model=AdvisoryOut)
async def get_advisory(
    advisory_id: str,
    actor: str = Depends(admin_required),
) -> AdvisoryOut:
    """Get a single advisory by ID.

    Args:
        advisory_id: Advisory ID

    Raises:
        404: Advisory not found
    """
    log.info("get_advisory", advisory_id=advisory_id, actor=actor)
    # TODO: Fetch advisory from persistence layer
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Advisory {advisory_id} not found",
    )


@router.post("/{advisory_id}/actions/dismiss", response_model=DismissActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def dismiss_advisory(
    advisory_id: str,
    actor: str = Depends(admin_required),
) -> DismissActionResponse:
    """Dismiss an advisory.

    Args:
        advisory_id: Advisory ID to dismiss

    Returns:
        Confirmation with 202 status
    """
    log.info("dismiss_advisory", advisory_id=advisory_id, actor=actor)
    # TODO: Mark advisory as dismissed in persistence layer
    return DismissActionResponse(ok=True)
