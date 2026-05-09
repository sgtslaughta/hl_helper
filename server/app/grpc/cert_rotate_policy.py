"""Server-side cert rotation policy: rate-limit, CSR validation, audit."""
from __future__ import annotations

import hmac
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from sqlalchemy.ext.asyncio import async_sessionmaker

log = logging.getLogger(__name__)


class RotationRateLimiter:
    """Per-host rotation rate limiter. 1 rotation per window by default."""

    def __init__(self, window_seconds: float = 3600.0) -> None:
        self._window = window_seconds
        self._last: dict[str, float] = {}
        self._lock = Lock()

    def allow(self, host_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last.get(host_id)
            if last is not None and now - last < self._window:
                return False
            self._last[host_id] = now
            return True


class CSRValidationError(Exception):
    """Raised when CSR fails validation."""


@dataclass
class CSRInfo:
    public_key_der: bytes
    common_name: str


def validate_csr(
    csr_pem: bytes,
    *,
    expected_cn: str,
    current_tls_pubkey_der: bytes | None = None,
) -> CSRInfo:
    """Parse + verify CSR. Returns info on success, raises on failure."""
    try:
        csr = x509.load_pem_x509_csr(csr_pem)
    except Exception as e:
        raise CSRValidationError(f"malformed CSR: {e}") from e

    if not csr.is_signature_valid:
        raise CSRValidationError("CSR signature invalid")

    cns = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cns or cns[0].value != expected_cn:
        raise CSRValidationError(
            f"CN mismatch: expected {expected_cn!r}, got "
            f"{cns[0].value if cns else None!r}"
        )

    pub_der = csr.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    if current_tls_pubkey_der is not None and pub_der == current_tls_pubkey_der:
        raise CSRValidationError(
            "forward-secrecy: CSR pubkey matches current TLS pubkey"
        )

    return CSRInfo(public_key_der=pub_der, common_name=expected_cn)


class PolicyDeniedError(Exception):
    """Rotation rejected by policy (identity / serial / etc)."""


class RateLimitedError(Exception):
    """Rotation rate limit exceeded."""


@dataclass
class RotationContext:
    host_id: str
    csr_pem: bytes
    signing_pubkey: bytes
    prev_serial: str
    peer_ip: str


@dataclass
class RotationResponse:
    cert_chain_pem: bytes
    not_after: datetime
    new_serial: str


class RotationOrchestrator:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker,
        ca,
        rate_limiter: RotationRateLimiter,
        ttl_days: int,
    ) -> None:
        self._sm = session_factory
        self._ca = ca
        self._rl = rate_limiter
        self._ttl = timedelta(days=ttl_days)

    async def rotate(self, ctx: RotationContext) -> RotationResponse:
        from server.app.models.host import Host
        from server.app.models.revoked_cert import RevokedCert

        if not self._rl.allow(ctx.host_id):
            raise RateLimitedError(f"rate limit: host={ctx.host_id}")

        async with self._sm() as session:
            host = await session.get(Host, ctx.host_id)
            if host is None:
                raise PolicyDeniedError(f"unknown host_id: {ctx.host_id}")

            # Constant-time compare for identity bytes
            if not hmac.compare_digest(
                bytes(host.agent_pubkey), bytes(ctx.signing_pubkey)
            ):
                raise PolicyDeniedError("signing_pubkey mismatch")

            if (host.cert_serial or "") != ctx.prev_serial:
                raise PolicyDeniedError(
                    f"prev_serial mismatch: stored={host.cert_serial!r} "
                    f"got={ctx.prev_serial!r}"
                )

            validate_csr(ctx.csr_pem, expected_cn=ctx.host_id)

            chain_pem, new_serial, not_after = self._ca.issue_host_cert(
                ctx.csr_pem, host_id=ctx.host_id, ttl=self._ttl
            )

            old_serial = host.cert_serial
            now = datetime.now(timezone.utc)
            host.cert_serial = new_serial
            host.cert_expires_at = not_after
            host.cert_rotated_at = now
            host.cert_rotation_count = (host.cert_rotation_count or 0) + 1

            if old_serial:
                session.add(
                    RevokedCert(
                        serial=old_serial,
                        host_id=ctx.host_id,
                        revoked_at=now,
                        reason="rotated",
                    )
                )

            await session.commit()

            log.info(
                "cert_rotated host=%s old=%s new=%s peer=%s",
                ctx.host_id,
                old_serial,
                new_serial,
                ctx.peer_ip,
            )

            return RotationResponse(
                cert_chain_pem=chain_pem,
                not_after=not_after,
                new_serial=new_serial,
            )
