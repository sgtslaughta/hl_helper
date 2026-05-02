"""Command model — represents a command sent to a host."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, Index, LargeBinary, String, UniqueConstraint, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class CommandRisk(str, Enum):
    """Risk level of a command."""

    LOW = "low"
    MED = "med"
    HIGH = "high"


class CommandStatus(str, Enum):
    """Status of a command."""

    QUEUED = "queued"
    IN_FLIGHT = "in_flight"
    ACKED = "acked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Command(Base):
    """Command table — represents a command sent to a host."""

    __tablename__ = "commands"
    __table_args__ = (
        Index("ix_command_task_run_id", "task_run_id"),
        Index("ix_command_host_id", "host_id"),
        UniqueConstraint("host_id", "sequence", name="uq_command_host_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_run_id: Mapped[str] = mapped_column(String(36), primary_key=False)
    host_id: Mapped[str] = mapped_column(String(36), primary_key=False)
    sequence: Mapped[int] = mapped_column(BigInteger)
    envelope_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    risk: Mapped[CommandRisk] = mapped_column(SQLEnum(CommandRisk))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[CommandStatus] = mapped_column(SQLEnum(CommandStatus))
