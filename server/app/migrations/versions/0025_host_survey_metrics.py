"""host_survey_metrics table updates

Revision ID: 0025_host_survey_metrics
Revises: 0024_terminal_recordings
Create Date: 2026-05-06 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_host_survey_metrics"
down_revision: Union[str, None] = "0024_terminal_recordings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("survey", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("survey_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("metrics", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("metrics_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("heartbeat_interval_s", sa.Integer(), nullable=False, server_default="30")
        )


def downgrade() -> None:
    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.drop_column("heartbeat_interval_s")
        batch_op.drop_column("metrics_at")
        batch_op.drop_column("metrics")
        batch_op.drop_column("survey_at")
        batch_op.drop_column("survey")
