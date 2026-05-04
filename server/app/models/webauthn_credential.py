"""WebAuthn credential model — stores registered FIDO2/WebAuthn keys per user."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base


class WebAuthnCredential(Base):
    """A registered WebAuthn credential (passkey / security key) for a user.

    `credential_id` and `public_key` are raw bytes as returned by the
    authenticator and the py_webauthn verification routines. `sign_count`
    is monotonically increasing — a regression is treated as a possible
    cloning event and the row is flagged via `flagged_at`.
    """

    __tablename__ = "webauthn_credentials"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    credential_id: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        unique=True,
        doc="Raw credential id from authenticator",
    )
    public_key: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, doc="COSE-encoded public key bytes"
    )
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aaguid: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    transports: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    backup_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_backed_up"
    )
    backup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    attestation_fmt: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    flagged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Set when sign-count regression detected (possible cloning).",
    )
