"""Webhook model — represents a webhook endpoint for event notifications.

C8 router pending; models scaffolded for future use.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class Webhook(Base):
    """Webhook table — represents a webhook endpoint for event notifications."""

    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    hmac_secret_ref: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    enabled: Mapped[bool] = mapped_column(
        default=True, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
