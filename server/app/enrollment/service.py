"""Enrollment service for agent provisioning."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import SigningBackend
from server.app.models.enrollment_token import EnrollmentToken
from server.app.models.host import Host

from .tokens import build_token, hash_token


class EnrollmentError(Exception):
    """Base enrollment error."""

    pass


class TokenNotFoundError(EnrollmentError):
    """Token not found."""

    pass


class TokenExpiredError(EnrollmentError):
    """Token has expired."""

    pass


class TokenAlreadyRedeemedError(EnrollmentError):
    """Token has already been redeemed."""

    pass


class CsrInvalidError(EnrollmentError):
    """Invalid CSR."""

    pass


@dataclass(frozen=True)
class EnrollmentResult:
    """Result of successful enrollment."""

    host_id: str
    leaf_cert_pem: bytes
    intermediate_cert_pem: bytes
    root_cert_pem: bytes
    server_signing_pubkey: bytes  # 32B Ed25519 raw
    grpc_endpoint: str


class EnrollmentService:
    """Service for managing enrollment tokens and host provisioning."""

    def __init__(
        self,
        ca: InternalCA,
        signing_backend: SigningBackend,
        *,
        grpc_endpoint: str,
        cert_ttl: timedelta = timedelta(hours=24),
    ) -> None:
        """Initialize enrollment service."""
        self.ca = ca
        self.signing_backend = signing_backend
        self.grpc_endpoint = grpc_endpoint
        self.cert_ttl = cert_ttl

    async def issue_token(
        self,
        session: AsyncSession,
        *,
        issued_by: str,
        ttl: timedelta = timedelta(minutes=15),
        note: str | None = None,
        now: datetime | None = None,
    ) -> tuple[str, EnrollmentToken]:
        """Generate + persist token; returns (plaintext, db_row).

        Plaintext shown to admin once; only hash stored.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        issued = build_token(ttl=ttl, now=now)

        token_row = EnrollmentToken(
            id=issued.token_id,
            token_hash=issued.token_hash,
            issued_by=issued_by,
            issued_at=issued.issued_at,
            expires_at=issued.expires_at,
            redeemed_at=None,
            redeemed_host_id=None,
            one_time=True,
            note=note,
        )

        session.add(token_row)
        return issued.plaintext, token_row

    async def redeem(
        self,
        session: AsyncSession,
        *,
        token_plaintext: str,
        csr_pem: bytes,
        hostname: str,
        agent_pubkey: bytes,  # raw 32B Ed25519
        now: datetime | None = None,
    ) -> EnrollmentResult:
        """Validate token, sign CSR, persist Host row, mark token redeemed.

        Atomic-ish: all writes happen within caller's session; caller commits.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Hash plaintext token. Query EnrollmentToken WHERE token_hash = hash.
        token_hash = hash_token(token_plaintext)
        stmt = select(EnrollmentToken).where(EnrollmentToken.token_hash == token_hash)
        result = await session.execute(stmt)
        tok = result.scalar_one_or_none()

        if tok is None:
            raise TokenNotFoundError("enrollment token not found")

        # 2. Check expiry
        if tok.expires_at.tzinfo is None:
            expires_at = tok.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = tok.expires_at

        if expires_at <= now:
            raise TokenExpiredError("enrollment token expired")

        # 3. Check not redeemed
        if tok.redeemed_at is not None:
            raise TokenAlreadyRedeemedError("enrollment token already redeemed")

        # 4. Generate host_id
        host_id = str(uuid.uuid4())

        # 5. Sign CSR
        try:
            leaf_pem = self.ca.issue_host_cert(csr_pem, host_id=host_id, ttl=self.cert_ttl)
        except Exception as e:
            raise CsrInvalidError("invalid CSR") from e

        # 6. Extract cert serial from leaf
        try:
            leaf_cert = x509.load_pem_x509_certificate(leaf_pem)
            cert_serial = hex(leaf_cert.serial_number)[2:]  # Remove '0x' prefix
        except Exception as e:
            raise CsrInvalidError("failed to parse issued certificate") from e

        # 7. Create Host row
        cert_expires_at = now + self.cert_ttl
        host = Host(
            id=host_id,
            hostname=hostname,
            agent_pubkey=agent_pubkey,
            cert_serial=cert_serial,
            cert_expires_at=cert_expires_at,
            enrolled_at=now,
            status="offline",
            labels={},
        )

        # 8. Update token row
        tok.redeemed_at = now
        tok.redeemed_host_id = host_id

        # 9. Persist both
        session.add(host)
        session.add(tok)

        # 10. Get intermediate and root PEM
        intermediate_cert_pem = self.ca.int_cert.public_bytes(serialization.Encoding.PEM)
        root_cert_pem = self.ca.root_cert.public_bytes(serialization.Encoding.PEM)

        # Get server signing pubkey (extract raw from PEM if needed)
        pubkey_bytes = self.signing_backend.public_key_bytes()
        try:
            # Try to parse as PEM (SubjectPublicKeyInfo format)
            pub = serialization.load_pem_public_key(pubkey_bytes)
            if isinstance(pub, ed25519.Ed25519PublicKey):
                server_signing_pubkey = pub.public_bytes(
                    encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
                )
            else:
                server_signing_pubkey = pubkey_bytes
        except Exception:
            # If it's already raw, use as-is
            server_signing_pubkey = pubkey_bytes

        return EnrollmentResult(
            host_id=host_id,
            leaf_cert_pem=leaf_pem,
            intermediate_cert_pem=intermediate_cert_pem,
            root_cert_pem=root_cert_pem,
            server_signing_pubkey=server_signing_pubkey,
            grpc_endpoint=self.grpc_endpoint,
        )
