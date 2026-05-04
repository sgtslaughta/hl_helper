"""Bootstrap token model — one-time admin provisioning tokens."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class BootstrapToken(Base):
    """Bootstrap token for one-time admin provisioning.

    Token is stored as SHA-256 hash (32 bytes). Raw token is shown ONCE to caller.
    Tokens expire after 60 minutes.
    """

    __tablename__ = "bootstrap_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="When token was consumed (redeemed)"
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_bootstrap_token_hash"),
    )

    @staticmethod
    def ttl_minutes() -> int:
        """Return TTL in minutes (60)."""
        return 60
