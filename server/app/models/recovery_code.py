"""Recovery code model — one-time-use MFA backup codes with hash storage."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class RecoveryCode(Base):
    """Recovery code table — one-time-use backup codes for MFA recovery.

    Codes are stored as SHA-256 hashes (32 bytes) only. Plaintext is never persisted.
    Each code can be consumed (used) once. Composite unique constraint on user_id + code_hash
    ensures no duplicate codes per user.
    """

    __tablename__ = "recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    code_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, doc="SHA-256 hash of plaintext code"
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="Timestamp when code was consumed"
    )
    viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when user viewed code list (for posture finding)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "code_hash", name="uq_recovery_user_hash"),)
