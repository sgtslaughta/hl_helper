"""Create plugins table.

Revision ID: 0022_plugins
Revises: 0021_oidc
Create Date: 2026-05-04 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_plugins"
down_revision: Union[str, None] = "0021_oidc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create plugins table."""
    op.create_table(
        "plugins",
        sa.Column("id", sa.String(200), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("manifest_json", sa.Text, nullable=False),
        sa.Column(
            "installed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()
        ),
        sa.Column("installed_by", sa.String(36), nullable=False),
        sa.Column("disabled_reason", sa.String(500), nullable=True),
        sa.Column("capability_ack_json", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_plugins_state", "state"),
    )


def downgrade() -> None:
    """Drop plugins table."""
    op.drop_table("plugins")
