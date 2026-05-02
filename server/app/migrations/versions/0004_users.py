"""users

Revision ID: 0004_users
Revises: 0003_groups
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_users"
down_revision: Union[str, None] = "0003_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("kind", sa.Enum("local", "oidc", name="userkind"), nullable=False),
        sa.Column("oidc_subject", sa.String(), nullable=True),
        sa.Column("oidc_issuer", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_table(
        "user_groups",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_user_group_name"),
    )
    op.create_table(
        "user_group_members",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("user_group_id", sa.String(36), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_group_id"], ["user_groups.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "user_group_id"),
    )
    op.create_index("ix_user_group_members_group_id", "user_group_members", ["user_group_id"])
    op.create_table(
        "service_accounts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_service_account_name"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False),
        sa.Column("last_4", sa.String(4), nullable=False),
        sa.Column("key_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("principal_id", sa.String(36), nullable=False),
        sa.Column("principal_kind", sa.Enum("user", "service_account", name="principalkind"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_allowlist", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_key_prefix", "api_keys", ["prefix"])
    op.create_index("ix_api_key_principal", "api_keys", ["principal_id", "principal_kind"])


def downgrade() -> None:
    op.drop_index("ix_api_key_principal", table_name="api_keys")
    op.drop_index("ix_api_key_prefix", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("service_accounts")
    op.drop_index("ix_user_group_members_group_id", table_name="user_group_members")
    op.drop_table("user_group_members")
    op.drop_table("user_groups")
    op.drop_table("users")
