"""MaintenanceWindow model — represents a maintenance or blackout window."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, Enum as SQLEnum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class MaintenanceWindowKind(str, Enum):
    """Kind of maintenance window."""

    ALLOW = "allow"
    BLACKOUT = "blackout"


class MaintenanceWindow(Base):
    """MaintenanceWindow table — represents a maintenance or blackout window."""

    __tablename__ = "maintenance_windows"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_maintenance_window_positive_duration"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    start_cron: Mapped[str] = mapped_column(String)
    duration_minutes: Mapped[int] = mapped_column(sa.Integer)
    timezone: Mapped[str] = mapped_column(String, default="UTC", server_default="UTC")
    target_selector: Mapped[dict[str, object]] = mapped_column(JSON)
    kind: Mapped[MaintenanceWindowKind] = mapped_column(
        SQLEnum(MaintenanceWindowKind)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
