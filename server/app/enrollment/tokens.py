"""Token generation and hashing for enrollment."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class IssuedToken:
    """Metadata for an issued enrollment token."""

    plaintext: str  # hlb_ prefix + base32 (no padding), ~58 chars
    token_id: str  # uuid
    token_hash: bytes  # sha256 of plaintext utf-8 bytes
    issued_at: datetime
    expires_at: datetime


def generate_token() -> str:
    """Return enrollment token: hlb_ prefix + base32(32 random bytes).

    Format: hlb_<base32>, where base32 is lowercase with no padding.
    ~256 bits entropy. ~58 chars total.
    """
    random_bytes = secrets.token_bytes(32)
    base32_encoded = base64.b32encode(random_bytes).decode("ascii")
    # Strip padding and lowercase for shorter UX and case consistency
    base32_clean = base32_encoded.rstrip("=").lower()
    return f"hlb_{base32_clean}"


def hash_token(plain: str) -> bytes:
    """Hash plaintext token with SHA-256."""
    return hashlib.sha256(plain.encode("utf-8")).digest()


def validate_token_shape(plain: str) -> None:
    """Validate enrollment token format.

    Must be: hlb_<base32> where base32 contains only a-z and 2-7 (lowercase).
    Raises ValueError if invalid.
    """
    if not plain.startswith("hlb_"):
        raise ValueError("Token must start with 'hlb_' prefix")

    suffix = plain[4:]  # Remove 'hlb_' prefix
    if not suffix:
        raise ValueError("Token must have content after 'hlb_' prefix")

    # Base32 alphabet: a-z2-7 (lowercase only, no padding)
    if not re.match(r"^[a-z2-7]+$", suffix):
        raise ValueError("Token must contain only lowercase a-z and 2-7 after prefix")


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


TTL_MIN_S = 60
TTL_MAX_S = 86_400
TTL_DEFAULT_S = 900


def clamp_ttl_seconds(value: int | None) -> int:
    """Validate and clamp enrollment-token TTL.

    Raises ValueError if below TTL_MIN_S; clamps above TTL_MAX_S; returns
    TTL_DEFAULT_S when None.
    """
    if value is None:
        return TTL_DEFAULT_S
    if value < TTL_MIN_S:
        raise ValueError(f"ttl_seconds must be >= {TTL_MIN_S}")
    return min(value, TTL_MAX_S)
