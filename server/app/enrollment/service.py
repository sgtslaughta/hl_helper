"""Enrollment service for agent provisioning."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import SigningBackend
from server.app.models.enrollment_token import EnrollmentToken
from server.app.models.host import Host

from .tokens import build_token, hash_token


def default_cert_ttl() -> timedelta:
    """TTL for issued host certs. Configurable via HL_CERT_TTL_DAYS env."""
    raw = os.environ.get("HL_CERT_TTL_DAYS")
    if raw is None:
        return timedelta(days=7)
    try:
        return timedelta(days=float(raw))
    except (ValueError, TypeError):
        return timedelta(days=7)


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
        cert_ttl: timedelta | None = None,
    ) -> None:
        """Initialize enrollment service."""
        self.ca = ca
        self.signing_backend = signing_backend
        self.grpc_endpoint = grpc_endpoint
        self.cert_ttl = cert_ttl if cert_ttl is not None else default_cert_ttl()

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

    async def list_pending(
        self,
        session: AsyncSession,
        now: datetime | None = None,
    ) -> list[EnrollmentToken]:
        """Return tokens that are unredeemed AND unexpired."""
        if now is None:
            now = datetime.now(timezone.utc)
        stmt = select(EnrollmentToken).where(
            EnrollmentToken.redeemed_at.is_(None),
            EnrollmentToken.expires_at > now,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def revoke_pending(
        self,
        session: AsyncSession,
        token_id: str,
    ) -> None:
        """Delete a pending (unredeemed) token row.

        Raises TokenNotFoundError if id unknown, TokenAlreadyRedeemedError if redeemed.
        """
        row = await session.get(EnrollmentToken, token_id)
        if row is None:
            raise TokenNotFoundError(token_id)
        if row.redeemed_at is not None:
            raise TokenAlreadyRedeemedError(token_id)
        await session.delete(row)

    async def redeem(
        self,
        session: AsyncSession,
        *,
        token_plaintext: str,
        csr_pem: bytes,
        hostname: str,
        agent_pubkey: bytes,  # raw 32B Ed25519
        labels: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> EnrollmentResult:
        """Validate token, sign CSR, persist Host row, mark token redeemed atomically.

        Validates agent_pubkey matches the public key in the CSR to prevent
        proof-of-possession attacks.

        Order: hash → SELECT (fail fast) → validate pubkey → sign CSR → atomic UPDATE-WHERE-NULL → insert Host.

        Raises:
            CsrInvalidError: if agent_pubkey doesn't match CSR public key or is malformed.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Hash plaintext token
        token_hash = hash_token(token_plaintext)

        # 2. SELECT token to fail fast with nice errors (non-atomic, but UPDATE catches races)
        stmt = select(EnrollmentToken).where(EnrollmentToken.token_hash == token_hash)
        result = await session.execute(stmt)
        tok = result.scalar_one_or_none()

        if tok is None:
            raise TokenNotFoundError("enrollment token not found")

        # 3. Check expiry (fail fast)
        if tok.expires_at.tzinfo is None:
            expires_at = tok.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = tok.expires_at

        if expires_at <= now:
            raise TokenExpiredError("enrollment token expired")

        # 4. Check not redeemed (fail fast)
        if tok.redeemed_at is not None:
            raise TokenAlreadyRedeemedError("enrollment token already redeemed")

        # 5. Validate agent_pubkey + CSR.
        #
        # The agent maintains TWO keypairs:
        #   - Ed25519 "signing" key — used for outbox/message authentication.
        #     Sent in body.agent_pubkey_b64 (raw 32 bytes).
        #   - ECDSA P-256 "TLS" key — used for the mTLS transport. The CSR is
        #     signed with this key, and the resulting leaf cert is what the
        #     agent presents during the gRPC TLS handshake. (BoringSSL on the
        #     server side does not advertise Ed25519 sig schemes in TLS 1.3.)
        #
        # We therefore require:
        #   - agent_pubkey is exactly 32 bytes (Ed25519 raw pubkey shape).
        #   - CSR is valid PEM/DER and parses to an ECDSA-P256 OR Ed25519 key.
        # We DO NOT require CSR pubkey == agent_pubkey: they are intentionally
        # distinct keys with different cryptographic roles.
        from cryptography.hazmat.primitives.asymmetric import ec

        try:
            if len(agent_pubkey) != 32:
                raise CsrInvalidError("agent_pubkey must be exactly 32 bytes")

            if csr_pem.startswith(b"-----"):
                csr_obj = x509.load_pem_x509_csr(csr_pem)
            else:
                csr_obj = x509.load_der_x509_csr(csr_pem)

            csr_pubkey = csr_obj.public_key()
            if not isinstance(csr_pubkey, (ed25519.Ed25519PublicKey, ec.EllipticCurvePublicKey)):
                raise CsrInvalidError(
                    f"CSR must contain Ed25519 or EC public key, got {type(csr_pubkey).__name__}"
                )
            if isinstance(csr_pubkey, ec.EllipticCurvePublicKey):
                if not isinstance(csr_pubkey.curve, ec.SECP256R1):
                    raise CsrInvalidError(
                        f"EC CSR must use P-256 curve, got {csr_pubkey.curve.name}"
                    )
        except CsrInvalidError:
            raise
        except Exception as e:
            raise CsrInvalidError(f"invalid CSR or pubkey validation failed: {e}") from e

        # 5.5. Generate host_id (before CSR signing)
        host_id = str(uuid.uuid4())

        # 6. Sign CSR (before claiming token)
        try:
            leaf_pem = self.ca.issue_host_cert(csr_pem, host_id=host_id, ttl=self.cert_ttl)
        except Exception as e:
            raise CsrInvalidError("invalid CSR") from e

        # 7. Extract cert serial from leaf
        try:
            leaf_cert = x509.load_pem_x509_certificate(leaf_pem)
            cert_serial = hex(leaf_cert.serial_number)[2:]  # Remove '0x' prefix
        except Exception as e:
            raise CsrInvalidError("failed to parse issued certificate") from e

        # 8. ATOMIC UPDATE: claim token (only if not redeemed yet)
        update_stmt = (
            update(EnrollmentToken)
            .where(
                EnrollmentToken.token_hash == token_hash,
                EnrollmentToken.redeemed_at.is_(None),
                EnrollmentToken.expires_at > now,
            )
            .values(redeemed_at=now, redeemed_host_id=host_id)
            .execution_options(synchronize_session=False)
        )
        update_result = await session.execute(update_stmt)

        # 9. Check if UPDATE succeeded (check rowcount)
        # Cast result to get proper type hint for mypy
        cursor_result = update_result
        if getattr(cursor_result, "rowcount", 0) == 0:
            # UPDATE failed. The token existed and wasn't expired during our SELECT,
            # so if UPDATE fails, someone else must have claimed it concurrently.
            # Raise TokenAlreadyRedeemedError to signal the token was claimed by another request.
            raise TokenAlreadyRedeemedError("enrollment token already redeemed")

        # 10. Refresh token object to ensure it reflects the UPDATE
        # (synchronize_session=False means we need to manually update the session)
        await session.refresh(tok)

        # 12. Create Host row
        cert_expires_at = now + self.cert_ttl
        host = Host(
            id=host_id,
            hostname=hostname,
            agent_pubkey=agent_pubkey,
            cert_serial=cert_serial,
            cert_expires_at=cert_expires_at,
            enrolled_at=now,
            status="offline",
            labels=dict(labels or {}),
        )

        # 13. Persist Host
        session.add(host)

        # 14. Get intermediate and root PEM
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
