"""ApiKey model — represents an API key for authentication."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SQLEnum, Index, JSON, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class PrincipalKind(str, Enum):
    """Type of principal that owns an API key."""

    USER = "user"
    SERVICE_ACCOUNT = "service_account"


class ApiKey(Base):
    """ApiKey table — represents an API key for user or service account authentication."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # prefix: first 8 chars of plaintext key (indexed for lookup)
    prefix: Mapped[str] = mapped_column(String(8))
    # last_4: last 4 chars of plaintext key
    last_4: Mapped[str] = mapped_column(String(4))
    # key_hash: SHA-256 of FULL plaintext key (including hlk_ prefix)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    # principal_id: points to either users.id or service_accounts.id (polymorphic, no FK constraint)
    # Reason: ApiKey can belong to either a User or ServiceAccount; we disambiguate with principal_kind
    principal_id: Mapped[str] = mapped_column(String(36))
    principal_kind: Mapped[PrincipalKind] = mapped_column(SQLEnum(PrincipalKind))
    name: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ip_allowlist: JSON list of CIDR strings
    ip_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_api_key_prefix", "prefix"),
        Index("ix_api_key_principal", "principal_id", "principal_kind"),
    )
