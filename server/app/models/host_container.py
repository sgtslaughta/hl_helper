"""HostContainer model for tracking containers on hosts."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, String, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class HostContainer(Base):
    """HostContainer table — containers running on a host."""

    __tablename__ = "host_containers"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hosts.id"), index=True
    )
    container_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256))
    image_ref: Mapped[str] = mapped_column(String(512))
    image_digest: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[str] = mapped_column(String(32))
    engine: Mapped[str] = mapped_column(String(16))
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("host_id", "container_id", name="uq_host_container"),
    )
