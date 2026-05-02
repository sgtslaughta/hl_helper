"""Token generation and hashing for enrollment."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class IssuedToken:
    """Metadata for an issued enrollment token."""

    plaintext: str  # base64url, ~43 chars
    token_id: str  # uuid
    token_hash: bytes  # sha256 of plaintext utf-8 bytes
    issued_at: datetime
    expires_at: datetime


def generate_token() -> str:
    """Return URL-safe random token, ~256 bits entropy. ~43 chars base64url."""
    return secrets.token_urlsafe(32)


def hash_token(plain: str) -> bytes:
    """Hash plaintext token with SHA-256."""
    return hashlib.sha256(plain.encode("utf-8")).digest()


def build_token(*, ttl: timedelta = timedelta(minutes=15), now: datetime | None = None) -> IssuedToken:
    """Construct an IssuedToken (does NOT persist)."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    plaintext = generate_token()
    token_hash = hash_token(plaintext)
    token_id = str(uuid.uuid4())
    issued_at = now
    expires_at = now + ttl

    return IssuedToken(
        plaintext=plaintext,
        token_id=token_id,
        token_hash=token_hash,
        issued_at=issued_at,
        expires_at=expires_at,
    )
