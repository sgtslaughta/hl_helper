"""Integrations API: stub for third-party integrations (Slack, PagerDuty, etc).

Stub implementation. TODO(C8/C-track): persist to DB.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])
log = structlog.get_logger(__name__)


class IntegrationCreate(BaseModel):
    """Request to create an integration."""
    name: str = Field(..., description="Integration name")
    kind: str = Field(..., description="Integration kind (slack, pagerduty, etc)")
    config: dict = Field(..., description="Integration-specific configuration")


class IntegrationOut(BaseModel):
    """Integration response."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Integration ID")
    name: str = Field(..., description="Integration name")
    kind: str = Field(..., description="Integration kind")
    config: dict = Field(..., description="Integration-specific configuration")


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(
    actor: str = Depends(admin_required),
) -> list[IntegrationOut]:
    """List all integrations (admin-gated).

    Returns:
        List of integrations.
    """
    # TODO(C8/C-track): persist to DB
    return []


@router.post("", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: IntegrationCreate,
    actor: str = Depends(admin_required),
) -> IntegrationOut:
    """Create a new integration.

    Args:
        body: Integration creation request (name, kind, config)

    Returns:
        Created integration with 201 status.
    """
    # TODO(C8/C-track): persist to DB
    integration_id = str(uuid4())
    return IntegrationOut(
        id=integration_id,
        name=body.name,
        kind=body.kind,
        config=body.config,
    )


@router.get("/{integration_id}", response_model=IntegrationOut)
async def get_integration(
    integration_id: str,
    actor: str = Depends(admin_required),
) -> IntegrationOut:
    """Get a single integration by ID (admin-gated).

    Raises:
        404: Integration not found.
    """
    # TODO(C8/C-track): persist to DB
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Integration {integration_id} not found",
    )


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: str,
    actor: str = Depends(admin_required),
) -> None:
    """Delete an integration.

    Args:
        integration_id: Integration to delete

    Raises:
        404: Integration not found.
    """
    # TODO(C8/C-track): persist to DB
    pass
