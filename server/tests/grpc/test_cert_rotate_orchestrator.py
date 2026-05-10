"""Tests for cert rotation orchestrator (DB-touching)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_rotate_happy_path(sm, fake_ca):
    from server.app.grpc.cert_rotate_policy import (
        RotationContext,
        RotationOrchestrator,
        RotationRateLimiter,
    )
    from server.app.models.host import Host
    from server.app.models.revoked_cert import RevokedCert
    from sqlalchemy import select

    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                cert_serial="OLDSERIAL",
                cert_rotation_count=0,
            )
        )
        await s.commit()

    csr_pem = _build_test_csr("h-1")
    orch = RotationOrchestrator(
        session_factory=sm,
        ca=fake_ca,
        rate_limiter=RotationRateLimiter(),
        ttl_days=7,
    )
    resp = await orch.rotate(
        RotationContext(
            host_id="h-1",
            csr_pem=csr_pem,
            signing_pubkey=b"\x00" * 32,
            prev_serial="OLDSERIAL",
            peer_ip="127.0.0.1",
        )
    )
    assert resp.cert_chain_pem
    assert resp.not_after > datetime.now(timezone.utc)

    async with sm() as s:
        host = await s.get(Host, "h-1")
        assert host.cert_serial != "OLDSERIAL"
        assert host.cert_rotation_count == 1
        rev = (
            await s.execute(
                select(RevokedCert).where(RevokedCert.serial == "OLDSERIAL")
            )
        ).scalar_one()
        assert rev.reason == "rotated"


@pytest.mark.asyncio
async def test_rotate_rejects_signing_pubkey_mismatch(sm, fake_ca):
    from server.app.grpc.cert_rotate_policy import (
        PolicyDeniedError,
        RotationContext,
        RotationOrchestrator,
        RotationRateLimiter,
    )
    from server.app.models.host import Host

    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                cert_serial="OLDSERIAL",
            )
        )
        await s.commit()

    orch = RotationOrchestrator(
        session_factory=sm,
        ca=fake_ca,
        rate_limiter=RotationRateLimiter(),
        ttl_days=7,
    )
    with pytest.raises(PolicyDeniedError, match="signing_pubkey"):
        await orch.rotate(
            RotationContext(
                host_id="h-1",
                csr_pem=_build_test_csr("h-1"),
                signing_pubkey=b"\xff" * 32,
                prev_serial="OLDSERIAL",
                peer_ip="127.0.0.1",
            )
        )


@pytest.mark.asyncio
async def test_rotate_rejects_prev_serial_mismatch(sm, fake_ca):
    from server.app.grpc.cert_rotate_policy import (
        PolicyDeniedError,
        RotationContext,
        RotationOrchestrator,
        RotationRateLimiter,
    )
    from server.app.models.host import Host

    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                cert_serial="CURRENT",
            )
        )
        await s.commit()

    orch = RotationOrchestrator(
        session_factory=sm,
        ca=fake_ca,
        rate_limiter=RotationRateLimiter(),
        ttl_days=7,
    )
    with pytest.raises(PolicyDeniedError, match="prev_serial"):
        await orch.rotate(
            RotationContext(
                host_id="h-1",
                csr_pem=_build_test_csr("h-1"),
                signing_pubkey=b"\x00" * 32,
                prev_serial="STALE",
                peer_ip="127.0.0.1",
            )
        )


@pytest.mark.asyncio
async def test_rotate_rate_limited(sm, fake_ca):
    from server.app.grpc.cert_rotate_policy import (
        RateLimitedError,
        RotationContext,
        RotationOrchestrator,
        RotationRateLimiter,
    )
    from server.app.models.host import Host

    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                cert_serial="OLDSERIAL",
            )
        )
        await s.commit()

    rl = RotationRateLimiter(window_seconds=3600)
    orch = RotationOrchestrator(
        session_factory=sm,
        ca=fake_ca,
        rate_limiter=rl,
        ttl_days=7,
    )
    ctx = RotationContext(
        host_id="h-1",
        csr_pem=_build_test_csr("h-1"),
        signing_pubkey=b"\x00" * 32,
        prev_serial="OLDSERIAL",
        peer_ip="127.0.0.1",
    )
    await orch.rotate(ctx)
    with pytest.raises(RateLimitedError):
        await orch.rotate(ctx)


def _build_test_csr(cn: str) -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        )
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM)
