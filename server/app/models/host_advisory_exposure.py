"""HostAdvisoryExposure — derived per-host per-advisory runtime exposure tier."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class HostAdvisoryExposure(Base):
    """Composite-PK row produced by derive_exposure() per posture scan."""

    __tablename__ = "host_advisory_exposure"

    host_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    advisory_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    exposure_tier: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_hae_advisory", "advisory_id"),
        Index("ix_hae_scanned_at", "scanned_at"),
    )
