"""groups

Revision ID: 0003_groups
Revises: 0002_revoked_certs
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_groups"
down_revision: Union[str, None] = "0002_revoked_certs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_group_name"),
    )
    op.create_table(
        "group_memberships",
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("static", "dynamic", name="membershipkind"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"]),
        sa.PrimaryKeyConstraint("host_id", "group_id"),
    )
    op.create_index("ix_group_memberships_group_id", "group_memberships", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_group_memberships_group_id", table_name="group_memberships")
    op.drop_table("group_memberships")
    op.drop_table("groups")
