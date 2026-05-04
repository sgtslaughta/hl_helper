"""Create totp_secrets table for encrypted TOTP secret storage.

Revision ID: 0018_totp_secrets
Revises: 0017_recovery_codes
Create Date: 2026-05-03 20:45:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_totp_secrets"
down_revision: Union[str, None] = "0017_recovery_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create totp_secrets table."""
    op.create_table(
        "totp_secrets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False, server_default="sha1"),
        sa.Column("digits", sa.Integer, nullable=False, server_default="6"),
        sa.Column("period_s", sa.Integer, nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_step", sa.Integer, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_totp_secret_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_totp_secret_user_id"),
        sa.Index("ix_totp_secret_user_id", "user_id"),
    )


def downgrade() -> None:
    """Drop totp_secrets table."""
    op.drop_table("totp_secrets")
