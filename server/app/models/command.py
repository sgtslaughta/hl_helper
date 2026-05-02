"""Command model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class Command(Base):
    """Command table — represents a command sent to a host."""

    __tablename__ = "commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int]
    nonce: Mapped[bytes]
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[str]
    risk: Mapped[str]  # 'low'|'medium'|'high'|'critical'
    payload_kind: Mapped[str]  # 'pkg_update'|'reboot'|'shell_exec'|...
    capability: Mapped[bytes | None] = mapped_column(nullable=True)
    signature: Mapped[bytes]
    envelope_blob: Mapped[bytes]  # full serialized CommandEnvelope
    status: Mapped[str]  # 'pending','dispatched','running','completed','failed'...
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_command_host_id", "host_id"),
        Index("ix_command_status", "status"),
        Index("ix_command_host_sequence", "host_id", "sequence"),
    )
