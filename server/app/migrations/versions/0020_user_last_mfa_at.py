"""Add users.last_mfa_at column for MFA step-up recency tracking.

Revision ID: 0020_user_last_mfa_at
Revises: 0019_webauthn_credentials
Create Date: 2026-05-04 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_user_last_mfa_at"
down_revision: Union[str, None] = "0019_webauthn_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_mfa_at column to users."""
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("last_mfa_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Drop last_mfa_at column from users."""
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_mfa_at")
