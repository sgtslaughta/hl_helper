"""TOTP secret model — encrypted time-based one-time password secrets."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class TotpSecret(Base):
    """TOTP secret table — stores encrypted TOTP secrets for MFA.

    Each user may have at most one active TOTP secret. The secret is encrypted
    at rest using AES-GCM. Enrollment is complete only when confirmed_at is set.
    """

    __tablename__ = "totp_secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, unique=True
    )
    secret_ciphertext: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, doc="AES-GCM encrypted TOTP secret blob"
    )
    algorithm: Mapped[str] = mapped_column(
        String(16), nullable=False, default="sha1", doc="HMAC algorithm: sha1, sha256, sha512"
    )
    digits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, doc="Number of digits in generated code"
    )
    period_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, doc="Time step in seconds"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_step: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="Last accepted step counter for replay prevention"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Null until first verify succeeds; enrollment unfinished otherwise",
    )

    __table_args__ = (
        Index("ix_totp_secret_user_id", "user_id"),
    )
