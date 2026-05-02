"""Result model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class Result(Base):
    """Result table — represents a result from a completed command."""

    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    command_id: Mapped[str] = mapped_column(String(36))  # FK loose to Command.id
    host_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str]  # 'ok','error','rejected','timeout'
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    stdout_blob: Mapped[bytes | None] = mapped_column(nullable=True)
    stderr_blob: Mapped[bytes | None] = mapped_column(nullable=True)
    final: Mapped[bool]
    prev_result_hash: Mapped[bytes | None] = mapped_column(nullable=True)
    signature: Mapped[bytes]

    __table_args__ = (
        Index("ix_result_command_id", "command_id"),
        Index("ix_result_host_id", "host_id"),
    )
