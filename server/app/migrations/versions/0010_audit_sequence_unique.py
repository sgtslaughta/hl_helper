"""add UNIQUE constraint to audit_entries.sequence for race condition safety

Revision ID: 0010_audit_sequence_unique
Revises: 0009_host_sequence
Create Date: 2026-05-03 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "0010_audit_sequence_unique"
down_revision: Union[str, None] = "0009_host_sequence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The sequence column is already the primary key, which enforces uniqueness.
    # This migration is a no-op but documents the intent.
    pass


def downgrade() -> None:
    pass
