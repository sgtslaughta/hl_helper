"""API key generation, hashing, and verification.

Plaintext format: `hlk_<43-char base64-url-safe random>` (32 random bytes encoded).
Stored:
  - prefix (str(8))    = first 8 chars of plaintext, indexed for lookup
  - last_4 (str(4))    = last 4 chars (display only)
  - key_hash (bytes 32) = SHA-256 of FULL plaintext including `hlk_` prefix
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models import ApiKey

PREFIX = "hlk_"


@dataclass(frozen=True)
class IssuedKey:
    """Represents an issued API key with plaintext and ID."""

    plaintext: str  # full key — return ONCE to caller
    api_key_id: str  # row id


def generate_plaintext() -> str:
    """Generate a plaintext API key.

    Format: hlk_<base64-url-safe of 32 random bytes>
    Total length: 4 + 43 = 47 chars
    """
    raw = secrets.token_bytes(32)
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return PREFIX + body


def hash_plaintext(plaintext: str) -> bytes:
    """Return SHA-256 hash of plaintext API key."""
    return hashlib.sha256(plaintext.encode("ascii")).digest()


def parse_prefix(plaintext: str) -> str:
    """Extract the prefix (first 8 chars) from plaintext."""
    return plaintext[:8]


def _ip_in_allowlist(source_ip: str, allowlist: list[str]) -> bool:
    """Return True iff source_ip falls inside any CIDR. Invalid CIDRs are skipped."""
    try:
        addr = ip_address(source_ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            net = ip_network(entry, strict=False)
        except ValueError:
            continue  # skip malformed stored CIDR
        if addr in net:
            return True
    return False


class ApiKeyError(Exception):
    """Base exception for API key errors."""

    pass


class ApiKeyExpired(ApiKeyError):
    """Raised when an API key has expired."""

    pass


class ApiKeyRevoked(ApiKeyError):
    """Raised when an API key has been revoked."""

    pass


class ApiKeyIPDenied(ApiKeyError):
    """Raised when the source IP is not in the allowlist."""

    pass


class ApiKeyService:
    """Service for issuing, verifying, and revoking API keys."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with a database session."""
        self._s = session

    async def issue(
        self,
        *,
        principal_id: str,
        principal_kind: str,
        name: str,
        expires_at: datetime | None = None,
        ip_allowlist: list[str] | None = None,
    ) -> IssuedKey:
        """Issue a new API key.

        Args:
            principal_id: ID of the user or service account owning this key
            principal_kind: "user" or "service_account"
            name: Human-readable name for this key
            expires_at: Optional expiration time (UTC)
            ip_allowlist: Optional list of CIDR strings allowed to use this key

        Returns:
            IssuedKey with plaintext and api_key_id

        Raises:
            ValueError: If any entry in ip_allowlist is not a valid CIDR string
        """
        # Validate CIDR strings before creating the row
        if ip_allowlist:
            for cidr in ip_allowlist:
                try:
                    ip_network(cidr, strict=False)
                except ValueError as e:
                    raise ValueError(f"invalid_cidr: {cidr}") from e

        plaintext = generate_plaintext()
        key = ApiKey(
            id=str(uuid.uuid4()),
            prefix=parse_prefix(plaintext),
            last_4=plaintext[-4:],
            key_hash=hash_plaintext(plaintext),
            principal_id=principal_id,
            principal_kind=principal_kind,
            name=name,
            expires_at=expires_at,
            ip_allowlist=ip_allowlist or [],
        )
        self._s.add(key)
        await self._s.flush()
        return IssuedKey(plaintext=plaintext, api_key_id=key.id)

    async def verify(
        self,
        plaintext: str,
        *,
        source_ip: str | None = None,
        now: datetime | None = None,
    ) -> ApiKey:
        """Verify an API key.

        Args:
            plaintext: The plaintext API key to verify
            source_ip: Optional source IP to check against allowlist.
                      If allowlist is non-empty and source_ip is None, raises ApiKeyIPDenied.
            now: Optional current time (defaults to now in UTC)

        Returns:
            The verified ApiKey row

        Raises:
            ApiKeyError: If key is invalid
            ApiKeyExpired: If key has expired
            ApiKeyRevoked: If key has been revoked
            ApiKeyIPDenied: If source_ip not in allowlist or source_ip missing when allowlist set
        """
        now = now or datetime.now(timezone.utc)
        digest = hash_plaintext(plaintext)
        prefix = parse_prefix(plaintext)

        # Lookup by prefix + verify hash equals digest in constant time
        rows = (await self._s.execute(select(ApiKey).where(ApiKey.prefix == prefix))).scalars().all()
        match: ApiKey | None = None
        for row in rows:
            # Constant-time comparison (secrets.compare_digest)
            if secrets.compare_digest(row.key_hash, digest):
                match = row
                break
        if match is None:
            raise ApiKeyError("invalid")

        if match.revoked_at is not None:
            raise ApiKeyRevoked("revoked")

        if match.expires_at is not None:
            exp = match.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now >= exp:
                raise ApiKeyExpired("expired")

        # Check IP allowlist: if non-empty, source_ip is required
        if match.ip_allowlist:
            if source_ip is None:
                raise ApiKeyIPDenied("ip_required")
            if not _ip_in_allowlist(source_ip, match.ip_allowlist):
                raise ApiKeyIPDenied("ip_not_allowed")

        match.last_used_at = now
        await self._s.flush()
        return match

    async def revoke(self, api_key_id: str, *, now: datetime | None = None) -> None:
        """Revoke an API key.

        Args:
            api_key_id: The ID of the key to revoke
            now: Optional time of revocation (defaults to now in UTC)

        Note:
            This method is idempotent: revoking a nonexistent or already-revoked
            key silently succeeds with no error.
        """
        now = now or datetime.now(timezone.utc)
        row = await self._s.scalar(select(ApiKey).where(ApiKey.id == api_key_id))
        if row is None or row.revoked_at is not None:
            return
        row.revoked_at = now
        await self._s.flush()
