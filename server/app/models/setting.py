"""Setting model — represents a system configuration setting."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SQLEnum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class SettingSource(str, Enum):
    """Source of a setting value."""

    RUNTIME = "runtime"
    ENV = "env"
    FILE = "file"
    DEFAULT = "default"


class SettingScope(str, Enum):
    """Scope/mutability of a setting."""

    BOOT_ONLY = "boot-only"
    RUNTIME_MUTABLE = "runtime-mutable"
    ENV_LOCKED = "env-locked"


class Setting(Base):
    """Setting table — represents a system configuration setting."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[SettingSource] = mapped_column(
        SQLEnum(SettingSource), nullable=False
    )
    scope: Mapped[SettingScope] = mapped_column(
        SQLEnum(SettingScope), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
