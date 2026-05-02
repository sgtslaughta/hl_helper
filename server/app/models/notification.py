"""Notification model — represents a notification provider configuration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SQLEnum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class NotificationProvider(str, Enum):
    """Supported notification providers."""

    SMTP = "smtp"
    WEBHOOK = "webhook"
    DISCORD = "discord"
    SLACK = "slack"
    TELEGRAM = "telegram"
    NTFY = "ntfy"
    GOTIFY = "gotify"
    PUSHOVER = "pushover"
    APPRISE = "apprise"
    MATRIX = "matrix"


class Notification(Base):
    """Notification table — represents a notification provider configuration."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    provider: Mapped[NotificationProvider] = mapped_column(
        SQLEnum(NotificationProvider), nullable=False
    )
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        default=True, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
