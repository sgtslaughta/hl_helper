"""Host model — represents an enrolled agent host."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.app.models.base import Base

if TYPE_CHECKING:
    from server.app.models.group_membership import GroupMembership


class Host(Base):
    """Host table — represents an enrolled agent host."""

    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hostname: Mapped[str]
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_pubkey: Mapped[bytes]  # Ed25519 raw, 32 bytes
    cert_serial: Mapped[str | None] = mapped_column(String, nullable=True)
    cert_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sequence: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String, default="offline")
    labels: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list[GroupMembership]] = relationship(
        "GroupMembership",
        foreign_keys="GroupMembership.host_id",
        back_populates=None,
    )

    __table_args__ = (
        Index("ix_host_hostname", "hostname"),
        Index("ix_host_status", "status"),
    )
