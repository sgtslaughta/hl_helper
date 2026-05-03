"""host sequences table for per-host monotonic command counters

Revision ID: 0009_host_sequence
Revises: 0008_misc
Create Date: 2026-05-02 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_host_sequence"
down_revision: Union[str, None] = "0008_misc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "host_sequences",
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column(
            "next_seq", sa.BigInteger(), nullable=False, server_default="1"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("host_id"),
    )


def downgrade() -> None:
    op.drop_table("host_sequences")
