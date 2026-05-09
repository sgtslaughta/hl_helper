"""cert rotation: host columns + enrollment_token purpose

Revision ID: 0033_cert_rotation
Revises: 0032_host_risk
Create Date: 2026-05-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_cert_rotation"
down_revision = "0032_host_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hosts",
        sa.Column("cert_rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosts",
        sa.Column(
            "cert_rotation_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "hosts",
        sa.Column("last_reenroll_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "enrollment_tokens",
        sa.Column(
            "purpose",
            sa.String(length=16),
            nullable=False,
            server_default="enroll",
        ),
    )
    op.add_column(
        "enrollment_tokens",
        sa.Column("bind_host_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enrollment_tokens", "bind_host_id")
    op.drop_column("enrollment_tokens", "purpose")
    op.drop_column("hosts", "last_reenroll_at")
    op.drop_column("hosts", "cert_rotation_count")
    op.drop_column("hosts", "cert_rotated_at")
