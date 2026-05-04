"""Create recovery_codes table for MFA backup codes.

Revision ID: 0017_recovery_codes
Revises: 0016_lockout_records
Create Date: 2026-05-03 20:45:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_recovery_codes"
down_revision: Union[str, None] = "0016_lockout_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create recovery_codes table."""
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_recovery_user_hash"),
        sa.Index("ix_recovery_codes_user_id", "user_id"),
    )


def downgrade() -> None:
    """Drop recovery_codes table."""
    op.drop_table("recovery_codes")
