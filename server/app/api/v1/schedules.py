"""Schedules API: CRUD for execution schedules.

Schedules define recurring or one-time actions via cron expressions.
TODO: Implement database persistence and cron scheduler integration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/schedules", tags=["schedules"])
log = structlog.get_logger(__name__)


class ScheduleCreate(BaseModel):
    """Request to create a new schedule."""

    name: str = Field(..., description="Schedule name")
    cron: str = Field(..., description="Cron expression (e.g., '0 9 * * MON')")
    action: str = Field(..., description="Action type (e.g., 'notify', 'run_check')")
    target: dict[str, Any] = Field(
        ..., description="Target configuration (action-dependent)"
    )


class ScheduleUpdate(BaseModel):
    """Request to update a schedule (partial)."""

    name: str | None = Field(None, description="Schedule name")
    cron: str | None = Field(None, description="Cron expression")
    action: str | None = Field(None, description="Action type")
    target: dict[str, Any] | None = Field(None, description="Target configuration")


class ScheduleOut(BaseModel):
    """Schedule response with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Schedule ID")
    name: str = Field(..., description="Schedule name")
    cron: str = Field(..., description="Cron expression")
    action: str = Field(..., description="Action type")
    target: dict[str, Any] = Field(..., description="Target configuration")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Last updated timestamp")


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(
    actor: str = Depends(admin_required),
) -> list[ScheduleOut]:
    """List all schedules (admin-gated).

    Returns:
        Empty list (TODO: fetch from database).
    """
    return []


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    actor: str = Depends(admin_required),
) -> ScheduleOut:
    """Create a new schedule.

    Args:
        body: Schedule creation request

    Returns:
        Created schedule with 201 status (TODO: save to database).
    """
    # TODO: Validate cron expression syntax
    # TODO: Insert into database, emit audit event
    schedule = ScheduleOut(
        id="sched_stub",
        name=body.name,
        cron=body.cron,
        action=body.action,
        target=body.target,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return schedule


@router.get("/{schedule_id}", response_model=ScheduleOut)
async def get_schedule(
    schedule_id: str,
    actor: str = Depends(admin_required),
) -> ScheduleOut:
    """Get a single schedule by ID (admin-gated).

    Args:
        schedule_id: Schedule ID

    Raises:
        404: Schedule not found.
    """
    # TODO: Fetch from database
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Schedule {schedule_id} not found",
    )


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    actor: str = Depends(admin_required),
) -> ScheduleOut:
    """Update a schedule (PATCH).

    Args:
        schedule_id: Schedule to update
        body: Fields to update

    Returns:
        Updated schedule.

    Raises:
        404: Schedule not found.
    """
    # TODO: Fetch from database, validate, update, emit audit event
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Schedule {schedule_id} not found",
    )


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    actor: str = Depends(admin_required),
) -> None:
    """Delete a schedule.

    Args:
        schedule_id: Schedule to delete

    Returns:
        204 No Content.
    """
    # TODO: Fetch from database, delete, emit audit event
    pass


@router.post("/{schedule_id}/actions/run-now", status_code=status.HTTP_202_ACCEPTED)
async def run_schedule_now(
    schedule_id: str,
    actor: str = Depends(admin_required),
) -> dict[str, bool]:
    """Trigger immediate execution of a schedule.

    Args:
        schedule_id: Schedule to execute

    Returns:
        {ok: True} with 202 Accepted.
    """
    # TODO: Queue immediate execution, validate schedule exists
    return {"ok": True}
