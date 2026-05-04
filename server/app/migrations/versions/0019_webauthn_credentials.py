"""Create webauthn_credentials table.

Revision ID: 0019_webauthn_credentials
Revises: 0018_totp_secrets
Create Date: 2026-05-04 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_webauthn_credentials"
down_revision: Union[str, None] = "0018_totp_secrets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("credential_id", sa.LargeBinary, nullable=False),
        sa.Column("public_key", sa.LargeBinary, nullable=False),
        sa.Column("sign_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("aaguid", sa.String(64), nullable=False, server_default=""),
        sa.Column("transports", sa.JSON, nullable=False),
        sa.Column("backup_state", sa.String(32), nullable=False, server_default="not_backed_up"),
        sa.Column("backup_eligible", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("attestation_fmt", sa.String(32), nullable=False, server_default="none"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_webauthn_credential_user_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "credential_id", name="ix_webauthn_credentials_credential_id"
        ),
    )
    op.create_index(
        "ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
