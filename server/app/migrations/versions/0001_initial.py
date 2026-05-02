"""initial

Revision ID: 0001_initial
Revises: None
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create hosts table
    op.create_table(
        "hosts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("hostname", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("agent_pubkey", sa.LargeBinary(), nullable=False),
        sa.Column("cert_serial", sa.String(), nullable=True),
        sa.Column("cert_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="offline"),
        sa.Column("labels", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_host_hostname", "hosts", ["hostname"])
    op.create_index("ix_host_status", "hosts", ["status"])

    # Create enrollment_tokens table
    op.create_table(
        "enrollment_tokens",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("issued_by", sa.String(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_host_id", sa.String(36), nullable=True),
        sa.Column("one_time", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_token_hash"),
    )
    op.create_index("ix_expires_at", "enrollment_tokens", ["expires_at"])

    # Create commands table
    op.create_table(
        "commands",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by", sa.String(), nullable=False),
        sa.Column("risk", sa.String(), nullable=False),
        sa.Column("payload_kind", sa.String(), nullable=False),
        sa.Column("capability", sa.LargeBinary(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("envelope_blob", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_command_host_id", "commands", ["host_id"])
    op.create_index("ix_command_status", "commands", ["status"])
    op.create_index("ix_command_host_sequence", "commands", ["host_id", "sequence"])

    # Create results table
    op.create_table(
        "results",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("command_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("stdout_blob", sa.LargeBinary(), nullable=True),
        sa.Column("stderr_blob", sa.LargeBinary(), nullable=True),
        sa.Column("final", sa.Boolean(), nullable=False),
        sa.Column("prev_result_hash", sa.LargeBinary(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_result_command_id", "results", ["command_id"])
    op.create_index("ix_result_host_id", "results", ["host_id"])

    # Create audit_entries table
    op.create_table(
        "audit_entries",
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.LargeBinary(), nullable=False),
        sa.Column("entry_hash", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("sequence"),
    )

    # Create audit_checkpoints table
    op.create_table(
        "audit_checkpoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("covers_sequence", sa.Integer(), nullable=False),
        sa.Column("merkle_root", sa.LargeBinary(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("signing_pubkey", sa.LargeBinary(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_checkpoints")
    op.drop_table("audit_entries")
    op.drop_table("results")
    op.drop_table("commands")
    op.drop_table("enrollment_tokens")
    op.drop_table("hosts")
