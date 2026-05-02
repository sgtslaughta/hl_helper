"""TaskRun model — represents execution of a task on a specific host."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class TaskRunStatus(str, Enum):
    """Status of a task run on a host."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class TaskRun(Base):
    """TaskRun table — represents execution of a task on a specific host."""

    __tablename__ = "task_runs"
    __table_args__ = (
        Index("ix_task_run_task_id", "task_id"),
        Index("ix_task_run_host_id", "host_id"),
        UniqueConstraint("task_id", "host_id", name="uq_task_run_per_host"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=False,
    )
    host_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=False,
    )
    status: Mapped[TaskRunStatus] = mapped_column(SQLEnum(TaskRunStatus))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
