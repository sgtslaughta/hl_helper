"""agent_releases table

Revision ID: 0026_agent_releases
Revises: 0025_host_survey_metrics
Create Date: 2026-05-07 14:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_agent_releases"
down_revision: Union[str, None] = "0025_host_survey_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_releases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("stable", "beta", "canary", name="releasechannel"),
            nullable=False,
        ),
        sa.Column("os", sa.String(length=16), nullable=False),
        sa.Column("arch", sa.String(length=16), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("manifest_json", sa.LargeBinary(), nullable=False),
        sa.Column("manifest_sig", sa.LargeBinary(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("staged", "published", "yanked", name="releasestatus"),
            nullable=False,
            server_default="staged",
        ),
        sa.Column("uploaded_by", sa.String(length=128), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("yanked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("yanked_reason", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version", "os", "arch", name="uq_agent_release_ver_os_arch"
        ),
    )
    op.create_index("ix_agent_releases_version", "agent_releases", ["version"])
    op.create_index("ix_agent_releases_channel", "agent_releases", ["channel"])
    op.create_index("ix_agent_releases_os", "agent_releases", ["os"])
    op.create_index("ix_agent_releases_arch", "agent_releases", ["arch"])
    op.create_index("ix_agent_releases_status", "agent_releases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_releases_status", table_name="agent_releases")
    op.drop_index("ix_agent_releases_arch", table_name="agent_releases")
    op.drop_index("ix_agent_releases_os", table_name="agent_releases")
    op.drop_index("ix_agent_releases_channel", table_name="agent_releases")
    op.drop_index("ix_agent_releases_version", table_name="agent_releases")
    op.drop_table("agent_releases")
