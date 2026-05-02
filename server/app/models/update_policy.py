"""UpdatePolicy model — represents an update policy for automatic updates."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SQLEnum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class RebootPolicy(str, Enum):
    """Reboot policy for updates."""

    NEVER = "never"
    IF_REQUIRED = "if_required"
    ALWAYS = "always"


class BreakingChangePolicy(str, Enum):
    """Breaking change policy for updates."""

    BLOCK = "block"
    APPROVE = "approve"
    ALLOW = "allow"


class UpdatePolicy(Base):
    """UpdatePolicy table — represents an update policy for automatic updates."""

    __tablename__ = "update_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    target_selector: Mapped[dict] = mapped_column(JSON)
    auto_apply_classes: Mapped[list[str]] = mapped_column(JSON)
    reboot_policy: Mapped[RebootPolicy] = mapped_column(SQLEnum(RebootPolicy))
    breaking_change_policy: Mapped[BreakingChangePolicy] = mapped_column(
        SQLEnum(BreakingChangePolicy)
    )
    approval_required: Mapped[bool] = mapped_column(
        default=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
