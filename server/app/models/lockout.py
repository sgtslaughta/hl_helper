"""Lockout record model — persistent account lockout tracking."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class LockoutRecord(Base):
    """Lockout record — tracks failure counts and lockout expiration for keys.

    Key format examples:
      - "user:<id>" for user-based lockouts
      - "ip:<addr>" for IP-based lockouts

    Fields:
      - key: Composite identifier (user:<id> or ip:<addr>), primary key
      - failure_count: Number of failures in current sliding window
      - last_failure_at: Timestamp of most recent failure
      - lockout_expires_at: When the current lockout expires (None if not locked)
      - level: Escalation level (0=none, 1=1m cooldown, 2=5m cooldown)
    """

    __tablename__ = "lockout_records"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Timestamp of most recent failure"
    )
    lockout_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="When lockout expires; None if not locked"
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, doc="Escalation level: 0=none, 1=1m, 2=5m"
    )
