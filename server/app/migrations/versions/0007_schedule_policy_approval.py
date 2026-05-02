"""schedule, maintenance_windows, update_policies, and approvals

Revision ID: 0007_schedule_policy_approval
Revises: 0006_tasks_commands
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_schedule_policy_approval"
down_revision: Union[str, None] = "0006_tasks_commands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("cron_expr", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("target_selector", sa.JSON(), nullable=False),
        sa.Column("payload_kind", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("missed_runs_policy", sa.Enum("skip", "catch_up_one", "catch_up_all", name="missedrunspolicy"), nullable=False, server_default="skip"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("start_cron", sa.String(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("target_selector", sa.JSON(), nullable=False),
        sa.Column("kind", sa.Enum("allow", "blackout", name="maintenancewindowkind"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("duration_minutes > 0", name="ck_maintenance_window_positive_duration"),
    )
    op.create_table(
        "update_policies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("target_selector", sa.JSON(), nullable=False),
        sa.Column("auto_apply_classes", sa.JSON(), nullable=False),
        sa.Column("reboot_policy", sa.Enum("never", "if_required", "always", name="rebootpolicy"), nullable=False),
        sa.Column("breaking_change_policy", sa.Enum("block", "approve", "allow", name="breakingchangepolicy"), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("subject_type", sa.Enum("command", "task", "policy_change", name="approvalsubjecttype"), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("policy", sa.Enum("single", "two_person", "single_second_factor", name="approvalpolicy"), nullable=False),
        sa.Column("requester_id", sa.String(36), nullable=False),
        sa.Column("state", sa.Enum("pending", "approved", "rejected", "expired", name="approvalstate"), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_proof", sa.String(), nullable=True),
        sa.Column("rejected_reason", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_approval_subject", "subject_type", "subject_id"),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("update_policies")
    op.drop_table("maintenance_windows")
    op.drop_table("schedules")
