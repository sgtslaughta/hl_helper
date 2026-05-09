"""host_risk

Revision ID: 0032_host_risk
Revises: 0031_advisory_catalog_split
Create Date: 2026-05-09

Per-host snapshot of the multi-pillar posture risk score. One row per
host; updated by RiskRecomputer on input changes. See
docs/superpowers/specs/2026-05-09-posture-risk-aggregator-design.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_host_risk"
down_revision = "0031_advisory_catalog_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_risk",
        sa.Column("host_id", sa.String(length=36), primary_key=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("pillars", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "floor_triggered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("score_prev", sa.Integer(), nullable=True),
        sa.Column("level_prev", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
    )
    op.create_index("host_risk_level_idx", "host_risk", ["level"])
    op.create_index(
        "host_risk_score_idx", "host_risk", [sa.text("score DESC")]
    )


def downgrade() -> None:
    op.drop_index("host_risk_score_idx", table_name="host_risk")
    op.drop_index("host_risk_level_idx", table_name="host_risk")
    op.drop_table("host_risk")
