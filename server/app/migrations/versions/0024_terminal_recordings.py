"""terminal_recordings table

Revision ID: 0024_terminal_recordings
Revises: 0023_plugin_role_perms
Create Date: 2026-05-05 16:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_terminal_recordings"
down_revision: Union[str, None] = "0023_plugin_role_perms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "terminal_recordings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("host_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asciicast_path", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_terminal_recordings_session_id", "terminal_recordings", ["session_id"])
    op.create_index("ix_terminal_recordings_host_id", "terminal_recordings", ["host_id"])
    op.create_index("ix_terminal_recordings_user_id", "terminal_recordings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_terminal_recordings_user_id", table_name="terminal_recordings")
    op.drop_index("ix_terminal_recordings_host_id", table_name="terminal_recordings")
    op.drop_index("ix_terminal_recordings_session_id", table_name="terminal_recordings")
    op.drop_table("terminal_recordings")
