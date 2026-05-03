"""Add pending_second state and first_decider_id to approvals; rename mfa_proof to mfa_proof_hash

Revision ID: 0011_approvals_two_person_state
Revises: 0010_audit_sequence_unique
Create Date: 2026-05-03 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_approvals_two_person_state"
down_revision: Union[str, None] = "0010_audit_sequence_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend ApprovalState enum to include pending_second
    # For SQLite: use VARCHAR storage (no native enum); for Postgres: ALTER TYPE
    try:
        # Try Postgres ALTER TYPE (will fail on SQLite but we catch that)
        op.execute("ALTER TYPE approvalstate ADD VALUE 'pending_second'")
    except Exception:
        # SQLite: enum is stored as VARCHAR, no DDL needed
        pass

    # Add first_decider_id column
    op.add_column("approvals", sa.Column("first_decider_id", sa.String(36), nullable=True))

    # Rename mfa_proof to mfa_proof_hash and change type to LargeBinary(32)
    # For SQLite: drop and recreate; for Postgres: use ALTER COLUMN
    inspector = sa.inspect(op.get_bind().engine)
    table_columns = {c["name"] for c in inspector.get_columns("approvals")}

    if "mfa_proof" in table_columns:
        # Drop old column and add new one with correct type
        op.drop_column("approvals", "mfa_proof")
        op.add_column("approvals", sa.Column("mfa_proof_hash", sa.LargeBinary(32), nullable=True))

    # Add payload column for metadata (used for degradation flags, etc.)
    op.add_column("approvals", sa.Column("payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "payload")
    op.drop_column("approvals", "mfa_proof_hash")
    op.add_column("approvals", sa.Column("mfa_proof", sa.String(), nullable=True))
    op.drop_column("approvals", "first_decider_id")
