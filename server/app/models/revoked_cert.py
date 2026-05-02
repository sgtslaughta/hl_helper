"""Revoked certificate model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class RevokedCert(Base):
    """RevokedCert table — tracks revoked host certificates."""

    __tablename__ = "revoked_certs"

    serial: Mapped[str] = mapped_column(String, primary_key=True)
    host_id: Mapped[str] = mapped_column(String, index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
