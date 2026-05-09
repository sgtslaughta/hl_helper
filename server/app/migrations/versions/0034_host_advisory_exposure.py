"""host_advisory_exposure: derived per-host per-advisory runtime exposure tier

Revision ID: 0034_host_advisory_exposure
Revises: 0033_cert_rotation
Create Date: 2026-05-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_host_advisory_exposure"
down_revision = "0033_cert_rotation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_advisory_exposure",
        sa.Column(
            "host_id",
            sa.String(length=36),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("advisory_id", sa.String(length=128), nullable=False),
        sa.Column("exposure_tier", sa.String(length=24), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("host_id", "advisory_id"),
    )
    op.create_index(
        "ix_hae_advisory", "host_advisory_exposure", ["advisory_id"]
    )
    op.create_index(
        "ix_hae_scanned_at", "host_advisory_exposure", ["scanned_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_hae_scanned_at", "host_advisory_exposure")
    op.drop_index("ix_hae_advisory", "host_advisory_exposure")
    op.drop_table("host_advisory_exposure")
