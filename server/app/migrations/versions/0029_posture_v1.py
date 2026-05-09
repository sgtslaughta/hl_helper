"""Posture v1 — advisories, affected packages, host packages, host advisories

Revision ID: 0029_posture_v1
Revises: 0028_host_sleep
Create Date: 2026-05-07 23:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_posture_v1"
down_revision: Union[str, None] = "0028_host_sleep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create advisories table
    op.create_table(
        "advisories",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("summary", sa.String(512), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=True),
        sa.Column(
            "severity", sa.String(16), nullable=False, server_default="unknown"
        ),
        sa.Column("cvss_v3", sa.String(64), nullable=True),
        sa.Column("cvss_v4", sa.String(64), nullable=True),
        sa.Column("epss", sa.Float(), nullable=True),
        sa.Column("kev", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_advisories_severity", "advisories", ["severity"])
    op.create_index("ix_advisories_epss", "advisories", ["epss"])
    op.create_index("ix_advisories_kev", "advisories", ["kev"])
    op.create_index("ix_advisories_modified", "advisories", ["modified"])

    # Create affected_packages table
    op.create_table(
        "affected_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("advisory_id", sa.String(128), nullable=False),
        sa.Column("ecosystem", sa.String(32), nullable=False),
        sa.Column("package", sa.String(256), nullable=False),
        sa.Column("introduced", sa.String(64), nullable=True),
        sa.Column("fixed", sa.String(64), nullable=True),
        sa.Column(
            "range_kind", sa.String(16), nullable=False, server_default="SEMVER"
        ),
        sa.ForeignKeyConstraint(["advisory_id"], ["advisories.id"], name="fk_affected_packages_advisory_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_affected_packages_advisory_id", "affected_packages", ["advisory_id"])
    op.create_index("ix_affected_packages_ecosystem", "affected_packages", ["ecosystem"])
    op.create_index("ix_affected_packages_package", "affected_packages", ["package"])
    op.create_index(
        "ix_affected_packages_ecosystem_package",
        "affected_packages",
        ["ecosystem", "package"],
    )

    # Create host_packages table
    op.create_table(
        "host_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("ecosystem", sa.String(32), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("arch", sa.String(32), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], name="fk_host_packages_host_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_id", "ecosystem", "name", name="uq_host_package"),
    )
    op.create_index("ix_host_packages_host_id", "host_packages", ["host_id"])
    op.create_index(
        "ix_host_packages_ecosystem_name", "host_packages", ["ecosystem", "name"]
    )

    # Create host_advisories table
    op.create_table(
        "host_advisories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("advisory_id", sa.String(128), nullable=False),
        sa.Column("package", sa.String(256), nullable=False),
        sa.Column("ecosystem", sa.String(32), nullable=False),
        sa.Column("current_version", sa.String(128), nullable=False),
        sa.Column("fixed_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppressed_by", sa.String(128), nullable=True),
        sa.Column("suppressed_reason", sa.String(512), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["advisory_id"], ["advisories.id"], name="fk_host_advisories_advisory_id"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], name="fk_host_advisories_host_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "host_id", "advisory_id", "package", name="uq_host_advisory"
        ),
    )
    op.create_index("ix_host_advisories_host_id", "host_advisories", ["host_id"])
    op.create_index("ix_host_advisories_advisory_id", "host_advisories", ["advisory_id"])
    op.create_index("ix_host_advisories_status", "host_advisories", ["status"])


def downgrade() -> None:
    op.drop_table("host_advisories")
    op.drop_table("host_packages")
    op.drop_table("affected_packages")
    op.drop_table("advisories")
