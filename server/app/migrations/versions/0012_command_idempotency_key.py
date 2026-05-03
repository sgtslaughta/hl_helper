"""Add idempotency_key column to commands table for durable deduplication.

Revision ID: 0012_command_idempotency_key
Revises: 0011_approvals_two_person_state
Create Date: 2026-05-03 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_command_idempotency_key"
down_revision: Union[str, None] = "0011_approvals_two_person_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite cannot ALTER to add constraints; use batch mode for portability.
    with op.batch_alter_table("commands") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))
        batch.create_unique_constraint(
            "uq_command_idempotency_key", ["idempotency_key"]
        )
    op.create_index("ix_command_idempotency_key", "commands", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_command_idempotency_key", table_name="commands")
    with op.batch_alter_table("commands") as batch:
        batch.drop_constraint("uq_command_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
