"""tasks, task_runs, and commands

Revision ID: 0006_tasks_commands
Revises: 0005_roles
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_tasks_commands"
down_revision: Union[str, None] = "0005_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old commands table (from 0001_initial)
    op.drop_table("commands")

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("kind", sa.Enum("pkg_update", "shell_exec", "reboot", "shutdown", "container_update", "file_transfer", "custom", name="taskkind"), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.Enum("pending", "approved", "running", "succeeded", "partial", "failed", "cancelled", "expired", name="taskstatus"), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("target_selector", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("risk", sa.Enum("low", "med", "high", name="taskrisk"), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_task_idempotency_key", "idempotency_key"),
    )
    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "succeeded", "failed", "skipped", "expired", name="taskrunstatus"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "host_id", name="uq_task_run_per_host"),
        sa.Index("ix_task_run_task_id", "task_id"),
        sa.Index("ix_task_run_host_id", "host_id"),
    )
    op.create_table(
        "commands",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_run_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("envelope_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("risk", sa.Enum("low", "med", "high", name="commandrisk"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("queued", "in_flight", "acked", "succeeded", "failed", "expired", "cancelled", name="commandstatus"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "sequence", name="uq_command_host_sequence"),
        sa.Index("ix_command_task_run_id", "task_run_id"),
        sa.Index("ix_command_host_id", "host_id"),
    )


def downgrade() -> None:
    op.drop_table("commands")
    op.drop_table("task_runs")
    op.drop_table("tasks")

    # Restore old commands table
    op.create_table(
        "commands",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by", sa.String(), nullable=False),
        sa.Column("risk", sa.String(), nullable=False),
        sa.Column("payload_kind", sa.String(), nullable=False),
        sa.Column("capability", sa.LargeBinary(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("envelope_blob", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_command_host_id", "commands", ["host_id"])
    op.create_index("ix_command_status", "commands", ["status"])
    op.create_index("ix_command_host_sequence", "commands", ["host_id", "sequence"])
