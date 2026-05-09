"""Add host_containers table for tracking containers on hosts.

Revision ID: 0030_host_containers
Revises: 0029_posture_v1
Create Date: 2026-05-07 23:40:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_host_containers"
down_revision: Union[str, None] = "0029_posture_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "host_containers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("container_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("image_ref", sa.String(512), nullable=False),
        sa.Column("image_digest", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("engine", sa.String(16), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], name="fk_host_containers_host_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "container_id", name="uq_host_container"),
    )
    op.create_index("ix_host_containers_host_id", "host_containers", ["host_id"])
    op.create_index("ix_host_containers_image_digest", "host_containers", ["image_digest"])


def downgrade() -> None:
    op.drop_table("host_containers")
