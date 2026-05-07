"""host agent version columns

Revision ID: 0027_host_agent_version
Revises: 0026_agent_releases
Create Date: 2026-05-07 14:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_host_agent_version"
down_revision: Union[str, None] = "0026_agent_releases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("agent_version", sa.String(length=64), nullable=True))
    op.add_column(
        "hosts",
        sa.Column("agent_version_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosts",
        sa.Column(
            "agent_update_status",
            sa.Enum(
                "idle",
                "downloading",
                "swapping",
                "healthchecking",
                "rolled_back",
                "failed",
                name="agentupdatestatus",
            ),
            nullable=False,
            server_default="idle",
        ),
    )
    op.add_column(
        "hosts",
        sa.Column("agent_update_target_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "hosts", sa.Column("pinned_release_id", sa.String(length=36), nullable=True)
    )
    op.create_index("ix_hosts_agent_version", "hosts", ["agent_version"])


def downgrade() -> None:
    op.drop_index("ix_hosts_agent_version", table_name="hosts")
    op.drop_column("hosts", "pinned_release_id")
    op.drop_column("hosts", "agent_update_target_version")
    op.drop_column("hosts", "agent_update_status")
    op.drop_column("hosts", "agent_version_updated_at")
    op.drop_column("hosts", "agent_version")
