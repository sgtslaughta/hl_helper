"""Create bootstrap_tokens table for one-time admin provisioning.

Revision ID: 0015_bootstrap_token
Revises: 0014_sessions
Create Date: 2026-05-03 19:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_bootstrap_token"
down_revision: Union[str, None] = "0014_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create bootstrap_tokens table."""
    op.create_table(
        "bootstrap_tokens",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_bootstrap_token_hash"),
        sa.Index("ix_bootstrap_token_expires_at", "expires_at"),
    )


def downgrade() -> None:
    """Drop bootstrap_tokens table."""
    op.drop_table("bootstrap_tokens")
