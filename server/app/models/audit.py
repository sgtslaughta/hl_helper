"""Audit models — DB-persisted audit chain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class AuditEntry(Base):
    """Audit entry — single operation in the audit chain."""

    __tablename__ = "audit_entries"

    sequence: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str]
    action: Mapped[str]
    subject: Mapped[str | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    prev_hash: Mapped[bytes]  # 32 bytes
    entry_hash: Mapped[bytes]  # 32 bytes


class AuditCheckpoint(Base):
    """Audit checkpoint — merkle root at a point in the chain."""

    __tablename__ = "audit_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    covers_sequence: Mapped[int]  # last entry seq covered (inclusive)
    merkle_root: Mapped[bytes]
    signature: Mapped[bytes]
    signing_pubkey: Mapped[bytes]
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
