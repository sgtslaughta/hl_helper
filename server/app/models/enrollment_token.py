"""EnrollmentToken model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class EnrollmentToken(Base):
    """Enrollment token for agent provisioning."""

    __tablename__ = "enrollment_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[bytes]  # SHA-256 of plaintext token (32 bytes)
    issued_by: Mapped[str]  # user/admin id
    issued_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    redeemed_host_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    one_time: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    purpose: Mapped[str] = mapped_column(
        String(16), nullable=False, default="enroll"
    )
    bind_host_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_token_hash"),
        Index("ix_expires_at", "expires_at"),
    )
