"""Webhooks API: stub for inbound and outbound webhooks.

Stub implementation. TODO(C8/C-track): persist to DB.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
log = structlog.get_logger(__name__)


class WebhookCreate(BaseModel):
    """Request to create a webhook."""
    name: str = Field(..., description="Webhook name")
    direction: str = Field(..., description="Direction: 'inbound' or 'outbound'")
    url: str = Field(..., description="Webhook URL")
    secret: str | None = Field(None, description="Optional signing secret")
    enabled: bool = Field(True, description="Whether webhook is enabled")


class WebhookOut(BaseModel):
    """Webhook response."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Webhook ID")
    name: str = Field(..., description="Webhook name")
    direction: str = Field(..., description="Direction: inbound or outbound")
    url: str = Field(..., description="Webhook URL")
    secret: str | None = Field(None, description="Optional signing secret")
    enabled: bool = Field(..., description="Whether webhook is enabled")


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    direction: Literal["inbound", "outbound"] | None = Query(None, description="Filter by direction"),
    actor: str = Depends(admin_required),
) -> list[WebhookOut]:
    """List all webhooks (admin-gated).

    Args:
        direction: Optional filter by direction (inbound or outbound)

    Returns:
        List of webhooks.
    """
    # TODO(C8/C-track): persist to DB, filter by direction if provided
    return []


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    actor: str = Depends(admin_required),
) -> WebhookOut:
    """Create a new webhook.

    Args:
        body: Webhook creation request (name, direction, url, secret?, enabled?)

    Returns:
        Created webhook with 201 status.
    """
    # TODO(C8/C-track): persist to DB
    webhook_id = str(uuid4())
    return WebhookOut(
        id=webhook_id,
        name=body.name,
        direction=body.direction,
        url=body.url,
        secret=body.secret,
        enabled=body.enabled,
    )


@router.get("/{webhook_id}", response_model=WebhookOut)
async def get_webhook(
    webhook_id: str,
    actor: str = Depends(admin_required),
) -> WebhookOut:
    """Get a single webhook by ID (admin-gated).

    Raises:
        404: Webhook not found.
    """
    # TODO(C8/C-track): persist to DB
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Webhook {webhook_id} not found",
    )


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: str,
    body: WebhookCreate,
    actor: str = Depends(admin_required),
) -> WebhookOut:
    """Update a webhook (PATCH).

    Raises:
        404: Webhook not found.
    """
    # TODO(C8/C-track): persist to DB
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Webhook {webhook_id} not found",
    )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    actor: str = Depends(admin_required),
) -> None:
    """Delete a webhook.

    Args:
        webhook_id: Webhook to delete

    Raises:
        404: Webhook not found.
    """
    # TODO(C8/C-track): persist to DB
    pass
