"""HostSequence: per-host monotonic counter for command ordering."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class HostSequence(Base):
    """HostSequence table — per-host monotonic counter for command ordering."""

    __tablename__ = "host_sequences"

    host_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    next_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
