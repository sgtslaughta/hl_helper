"""Session model — opaque token sessions with IP/UA binding and MFA tracking."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class Session(Base):
    """Session table — represents an authenticated session with optional MFA validation.

    Token is stored as SHA-256 hash (32 bytes) for security. IP class uses CIDR notation
    for binding (e.g., "10.0.0.0/24"). User agent fingerprint is also hashed.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)
    mfa_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc='MFA level: "none", "totp", "webauthn", "step_up"',
    )
    ip_class: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="CIDR-style IP binding (e.g., 10.0.0.0/24)",
    )
    ua_fp: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, doc="32-byte hash of user agent fingerprint"
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Last time this session was used"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Revocation timestamp if revoked"
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
