"""Schedule model — represents a scheduled task to be executed across hosts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SQLEnum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class MissedRunsPolicy(str, Enum):
    """Policy for handling missed scheduled runs."""

    SKIP = "skip"
    CATCH_UP_ONE = "catch_up_one"
    CATCH_UP_ALL = "catch_up_all"


class Schedule(Base):
    """Schedule table — represents a scheduled task to be executed across hosts."""

    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    cron_expr: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String, default="UTC", server_default="UTC")
    enabled: Mapped[bool] = mapped_column(
        default=True, server_default=sa.true()
    )
    target_selector: Mapped[dict[str, object]] = mapped_column(JSON)
    payload_kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    missed_runs_policy: Mapped[MissedRunsPolicy] = mapped_column(
        SQLEnum(MissedRunsPolicy), default=MissedRunsPolicy.SKIP, server_default=MissedRunsPolicy.SKIP
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
