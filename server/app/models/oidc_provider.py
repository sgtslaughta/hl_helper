"""OIDC provider model — registered identity providers."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


def _default_scopes() -> list[str]:
    return ["openid", "email", "profile"]


class OidcProvider(Base):
    """OIDC provider configuration.

    Stores the metadata needed to discover and complete an OIDC/OAuth2 flow.
    `client_secret_ref` is a SecretRef string (e.g. ``secret://local/oidc/<id>#client_secret``)
    so the actual secret never lives in this row.
    """

    __tablename__ = "oidc_providers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False)
    client_secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=_default_scopes, nullable=False)
    claim_mappings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preset_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discovery_cache: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    discovery_cached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    button_asset: Mapped[str | None] = mapped_column(String(256), nullable=True)
    oauth2_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorization_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    token_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    userinfo_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jwks_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
