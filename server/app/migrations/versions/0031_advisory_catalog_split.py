"""Advisory catalog split: drop FK from host_advisories.advisory_id, add feed_status.

This migration prepares the schema for the dual-engine advisory catalog. On
SQLite the catalog tables (advisories, affected_packages, feed_status) move
to a separate ``advisory.db`` file managed by the catalog engine; on
Postgres they continue to live in the same database. Either way:

  * The ``host_advisories.advisory_id`` foreign key is dropped — references
    are now opaque strings (matcher tolerates missing rows).
  * ``feed_status`` is created in the main DB so deployments without a
    separate catalog file still have a place to record sync state.

Existing advisory data in the main DB is left in place; the worker's first
run will repopulate the catalog (Postgres) or the new file (SQLite).

Revision ID: 0031_advisory_catalog_split
Revises: 0030_host_containers
Create Date: 2026-05-08 14:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0031_advisory_catalog_split"
down_revision: Union[str, None] = "0030_host_containers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the FK from host_advisories.advisory_id. SQLite cannot ALTER FK
    # in place; use batch_alter_table for portability.
    with op.batch_alter_table("host_advisories") as batch_op:
        try:
            batch_op.drop_constraint("fk_host_advisories_advisory_id", type_="foreignkey")
        except Exception:
            pass  # constraint may have been auto-named or already absent

    # Create feed_status if not present.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "feed_status" not in inspector.get_table_names():
        op.create_table(
            "feed_status",
            sa.Column("feed_name", sa.String(32), primary_key=True),
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.String(1024), nullable=True),
            sa.Column("next_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("feed_status")
    # No restore of the FK on advisory_id — schema parity with new code.
