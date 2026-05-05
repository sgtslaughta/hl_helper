"""Containers API: stub for container lifecycle management."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/containers", tags=["containers"])
log = structlog.get_logger(__name__)


class ContainerOut(BaseModel):
    """Container response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Container ID")
    host_id: str = Field(..., description="Host ID")
    state: str = Field(..., description="Container state")


class ActionResponse(BaseModel):
    """Response for action execution."""

    ok: bool = Field(..., description="Action success indicator")
    action: str = Field(..., description="Action performed")


@router.get("", response_model=list[ContainerOut])
async def list_containers(
    host_id: str | None = None,
    state: str | None = None,
    actor: str = Depends(admin_required),
) -> list[ContainerOut]:
    """List containers with optional filtering.

    Args:
        host_id: Filter by host ID (optional)
        state: Filter by state (optional)

    Returns:
        Empty list (TODO: fetch from persistence layer)
    """
    log.info("list_containers", host_id=host_id, state=state, actor=actor)
    # TODO: Query containers from persistence layer with filters
    return []


@router.get("/{container_id}", response_model=ContainerOut)
async def get_container(
    container_id: str,
    actor: str = Depends(admin_required),
) -> ContainerOut:
    """Get a single container by ID.

    Args:
        container_id: Container ID

    Raises:
        404: Container not found
    """
    log.info("get_container", container_id=container_id, actor=actor)
    # TODO: Fetch container from persistence layer
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Container {container_id} not found",
    )


@router.post("/{container_id}/actions/{action}", response_model=ActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_container_action(
    container_id: str,
    action: str,
    actor: str = Depends(admin_required),
) -> ActionResponse:
    """Execute an action on a container (start, stop, restart).

    Args:
        container_id: Container ID
        action: Action to execute (start, stop, restart)

    Returns:
        Confirmation with action name and 202 status

    Raises:
        400: If action is not in (start, stop, restart)
    """
    valid_actions = {"start", "stop", "restart"}
    if action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}",
        )

    log.info("execute_container_action", container_id=container_id, action=action, actor=actor)
    # TODO: Execute action against container runtime
    return ActionResponse(ok=True, action=action)
