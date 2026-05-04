"""Create lockout_records table for persistent account lockout tracking.

Revision ID: 0016_lockout_records
Revises: 0015_bootstrap_token
Create Date: 2026-05-03 20:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_lockout_records"
down_revision: Union[str, None] = "0015_bootstrap_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create lockout_records table."""
    op.create_table(
        "lockout_records",
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lockout_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("key"),
        sa.Index("ix_lockout_expires_at", "lockout_expires_at"),
    )


def downgrade() -> None:
    """Drop lockout_records table."""
    op.drop_table("lockout_records")
