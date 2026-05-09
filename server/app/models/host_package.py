"""HostPackage model for tracking packages installed on hosts."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, String, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class HostPackage(Base):
    """HostPackage table — packages installed on a host."""

    __tablename__ = "host_packages"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hosts.id"), index=True
    )
    ecosystem: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(256))
    version: Mapped[str] = mapped_column(String(128))
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    arch: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("host_id", "ecosystem", "name", name="uq_host_package"),
        Index("ix_host_packages_ecosystem_name", "ecosystem", "name"),
    )
