"""revoked_certs

Revision ID: 0002_revoked_certs
Revises: 0001_initial
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_revoked_certs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_certs",
        sa.Column("serial", sa.String(), nullable=False),
        sa.Column("host_id", sa.String(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("serial"),
    )
    op.create_index("ix_revoked_certs_host_id", "revoked_certs", ["host_id"])


def downgrade() -> None:
    op.drop_index("ix_revoked_certs_host_id", table_name="revoked_certs")
    op.drop_table("revoked_certs")
