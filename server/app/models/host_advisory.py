"""HostAdvisory model for tracking advisories affecting hosts."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, String, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class HostAdvisory(Base):
    """HostAdvisory table — security advisories affecting a host."""

    __tablename__ = "host_advisories"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hosts.id"), index=True
    )
    # Opaque reference into the advisory catalog (advisories.id). No FK
    # because the catalog may live in a separate database file on SQLite,
    # or, in future, be hosted by a different service. Validation happens
    # at insert time.
    advisory_id: Mapped[str] = mapped_column(String(128), index=True)
    package: Mapped[str] = mapped_column(String(256))
    ecosystem: Mapped[str] = mapped_column(String(32))
    current_version: Mapped[str] = mapped_column(String(128))
    fixed_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open"
    )
    suppressed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suppressed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    suppressed_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "host_id", "advisory_id", "package", name="uq_host_advisory"
        ),
        Index("ix_host_advisories_status", "status"),
    )
