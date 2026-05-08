"""host sleep columns

Revision ID: 0028_host_sleep
Revises: 0027_host_agent_version
Create Date: 2026-05-07 16:45:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_host_sleep"
down_revision: Union[str, None] = "0027_host_agent_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("sleeping", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "hosts",
        sa.Column("sleep_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hosts", "sleep_until")
    op.drop_column("hosts", "sleeping")
