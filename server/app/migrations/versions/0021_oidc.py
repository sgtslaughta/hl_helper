"""Create oidc_providers + oidc_account_links tables.

Revision ID: 0021_oidc
Revises: 0020_user_last_mfa_at
Create Date: 2026-05-04 00:00:00.000000

Note: parallel migrations (0019_webauthn_credentials, 0020_user_last_mfa_at)
forced this to land at 0021 instead of the original 0019 reservation.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_oidc"
down_revision: Union[str, None] = "0020_user_last_mfa_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create oidc_providers and oidc_account_links."""
    op.create_table(
        "oidc_providers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("client_id", sa.String(256), nullable=False),
        sa.Column("client_secret_ref", sa.String(512), nullable=True),
        sa.Column("scopes", sa.JSON, nullable=False),
        sa.Column("claim_mappings", sa.JSON, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("preset_kind", sa.String(64), nullable=True),
        sa.Column("discovery_cache", sa.JSON, nullable=True),
        sa.Column("discovery_cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("button_asset", sa.String(256), nullable=True),
        sa.Column("oauth2_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("authorization_endpoint", sa.String(512), nullable=True),
        sa.Column("token_endpoint", sa.String(512), nullable=True),
        sa.Column("userinfo_endpoint", sa.String(512), nullable=True),
        sa.Column("jwks_uri", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_oidc_provider_name"),
    )
    op.create_table(
        "oidc_account_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider_id", sa.String(36), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["oidc_providers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "subject", name="uq_oidc_link_provider_sub"),
        sa.Index("ix_oidc_link_user_id", "user_id"),
        sa.Index("ix_oidc_link_provider_id", "provider_id"),
    )


def downgrade() -> None:
    """Drop OIDC tables."""
    op.drop_table("oidc_account_links")
    op.drop_table("oidc_providers")
