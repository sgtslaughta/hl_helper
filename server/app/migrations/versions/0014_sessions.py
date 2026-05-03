"""Create sessions table for opaque token sessions with IP/UA binding.

Revision ID: 0014_sessions
Revises: 0013_seed_bootstrap_admin
Create Date: 2026-05-03 19:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_sessions"
down_revision: Union[str, None] = "0013_seed_bootstrap_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sessions table with token_hash UNIQUE constraint."""
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("mfa_level", sa.String(16), nullable=False),
        sa.Column("ip_class", sa.String(64), nullable=False),
        sa.Column("ua_fp", sa.LargeBinary(32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
        sa.Index("ix_session_user_id", "user_id"),
    )


def downgrade() -> None:
    """Drop sessions table."""
    op.drop_table("sessions")
