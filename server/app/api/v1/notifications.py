"""Notifications API: stub for notification channels (email, slack, webhook, etc).

Stub implementation. TODO(C8/C-track): persist to DB.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])
log = structlog.get_logger(__name__)


class NotificationChannelCreate(BaseModel):
    """Request to create a notification channel."""
    name: str = Field(..., description="Channel name")
    type: str = Field(..., description="Channel type (email, slack, webhook, etc)")
    target: str = Field(..., description="Target address or URL")
    enabled: bool = Field(True, description="Whether channel is enabled")


class NotificationChannelOut(BaseModel):
    """Notification channel response."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Channel ID")
    name: str = Field(..., description="Channel name")
    type: str = Field(..., description="Channel type")
    target: str = Field(..., description="Target address or URL")
    enabled: bool = Field(..., description="Whether channel is enabled")


class NotificationTestRequest(BaseModel):
    """Request to test a notification channel."""
    channel_id: str = Field(..., description="Channel ID to test")


class NotificationTestResponse(BaseModel):
    """Response from test request."""
    ok: bool = Field(..., description="Whether test was queued successfully")
    message: str = Field(..., description="Status message")


class UnreadCount(BaseModel):
    """Count of unread notifications for current principal."""
    count: int = Field(..., description="Unread notification count")


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(actor: str = Depends(admin_required)) -> UnreadCount:
    """Return unread notification count. Stub: returns 0 until C8 wires events."""
    return UnreadCount(count=0)


@router.get("", response_model=list[NotificationChannelOut])
async def list_notification_channels(
    actor: str = Depends(admin_required),
) -> list[NotificationChannelOut]:
    """List all notification channels (admin-gated).

    Returns:
        List of notification channels.
    """
    # TODO(C8/C-track): persist to DB
    return []


@router.post("", response_model=NotificationChannelOut, status_code=status.HTTP_201_CREATED)
async def create_notification_channel(
    body: NotificationChannelCreate,
    actor: str = Depends(admin_required),
) -> NotificationChannelOut:
    """Create a new notification channel.

    Args:
        body: Channel creation request (name, type, target, enabled?)

    Returns:
        Created channel with 201 status.
    """
    # TODO(C8/C-track): persist to DB
    channel_id = str(uuid4())
    return NotificationChannelOut(
        id=channel_id,
        name=body.name,
        type=body.type,
        target=body.target,
        enabled=body.enabled,
    )


@router.get("/{channel_id}", response_model=NotificationChannelOut)
async def get_notification_channel(
    channel_id: str,
    actor: str = Depends(admin_required),
) -> NotificationChannelOut:
    """Get a single notification channel by ID (admin-gated).

    Raises:
        404: Channel not found.
    """
    # TODO(C8/C-track): persist to DB
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Notification channel {channel_id} not found",
    )


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification_channel(
    channel_id: str,
    actor: str = Depends(admin_required),
) -> None:
    """Delete a notification channel.

    Args:
        channel_id: Channel to delete

    Raises:
        404: Channel not found.
    """
    # TODO(C8/C-track): persist to DB
    pass


@router.post("/test", response_model=NotificationTestResponse, status_code=status.HTTP_202_ACCEPTED)
async def test_notification_channel(
    body: NotificationTestRequest,
    actor: str = Depends(admin_required),
) -> NotificationTestResponse:
    """Queue a test of a notification channel.

    Args:
        body: Test request with channel_id

    Returns:
        Status with 202 Accepted.
    """
    # TODO(C8/C-track): persist to DB, queue async task
    return NotificationTestResponse(ok=True, message="test queued")
