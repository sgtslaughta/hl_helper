"""Task model — represents a task to be executed across hosts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SQLEnum, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class TaskKind(str, Enum):
    """Kind of task to execute."""

    PKG_UPDATE = "pkg_update"
    SHELL_EXEC = "shell_exec"
    REBOOT = "reboot"
    SHUTDOWN = "shutdown"
    CONTAINER_UPDATE = "container_update"
    FILE_TRANSFER = "file_transfer"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    """Status of a task."""

    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TaskRisk(str, Enum):
    """Risk level of a task."""

    LOW = "low"
    MED = "med"
    HIGH = "high"


class Task(Base):
    """Task table — represents a task to be executed across hosts."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_task_idempotency_key", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[TaskKind] = mapped_column(SQLEnum(TaskKind))
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus), default=TaskStatus.PENDING, server_default=TaskStatus.PENDING
    )
    payload: Mapped[dict] = mapped_column(JSON)
    target_selector: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    risk: Mapped[TaskRisk] = mapped_column(SQLEnum(TaskRisk))
    requires_approval: Mapped[bool] = mapped_column(
        default=False, server_default=sa.false()
    )
