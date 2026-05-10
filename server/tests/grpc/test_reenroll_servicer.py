"""Tests for ReEnroll servicer Challenge and Complete RPCs."""
from __future__ import annotations

import pytest


def _ctx():
    """Mock grpc.ServicerContext capturing abort code."""
    class C:
        aborted_code = None
        aborted_detail = None

        async def abort(self, code, detail):
            self.aborted_code = code
            self.aborted_detail = detail
            raise Exception(f"aborted: {code} {detail}")

        def peer(self):
            return "ipv4:127.0.0.1:1234"

    return C()


@pytest.mark.asyncio
async def test_challenge_returns_nonce_for_known_host(sm):
    from server.app.grpc._pb.fleet.v1 import reenroll_pb2
    from server.app.grpc.reenroll_servicer import ReEnrollServicer
    from server.app.grpc.reenroll_state import NonceCache, ReEnrollRateLimiter
    from server.app.models.host import Host

    pubkey = b"\x11" * 32
    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=pubkey))
        await s.commit()

    svc = ReEnrollServicer(
        session_factory=sm,
        nonce_cache=NonceCache(),
        rate_limiter=ReEnrollRateLimiter(),
        ca=None,
        ttl_days=7,
    )

    req = reenroll_pb2.ChallengeRequest(host_id="h-1", signing_pubkey=pubkey)
    resp = await svc.Challenge(req, _ctx())
    assert len(resp.nonce) == 32


@pytest.mark.asyncio
async def test_challenge_rejects_unknown_host(sm):
    import grpc

    from server.app.grpc._pb.fleet.v1 import reenroll_pb2
    from server.app.grpc.reenroll_servicer import ReEnrollServicer
    from server.app.grpc.reenroll_state import NonceCache, ReEnrollRateLimiter

    svc = ReEnrollServicer(
        session_factory=sm,
        nonce_cache=NonceCache(),
        rate_limiter=ReEnrollRateLimiter(),
        ca=None,
        ttl_days=7,
    )
    ctx = _ctx()
    req = reenroll_pb2.ChallengeRequest(host_id="nope", signing_pubkey=b"\x00" * 32)
    with pytest.raises(Exception):
        await svc.Challenge(req, ctx)
    assert ctx.aborted_code == grpc.StatusCode.NOT_FOUND


@pytest.mark.asyncio
async def test_challenge_rejects_wrong_pubkey(sm):
    import grpc

    from server.app.grpc._pb.fleet.v1 import reenroll_pb2
    from server.app.grpc.reenroll_servicer import ReEnrollServicer
    from server.app.grpc.reenroll_state import NonceCache, ReEnrollRateLimiter
    from server.app.models.host import Host

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=b"\x11" * 32))
        await s.commit()

    svc = ReEnrollServicer(
        session_factory=sm,
        nonce_cache=NonceCache(),
        rate_limiter=ReEnrollRateLimiter(),
        ca=None,
        ttl_days=7,
    )
    ctx = _ctx()
    req = reenroll_pb2.ChallengeRequest(host_id="h-1", signing_pubkey=b"\xff" * 32)
    with pytest.raises(Exception):
        await svc.Challenge(req, ctx)
    assert ctx.aborted_code == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_complete_happy_path(sm, fake_ca):
    import time

    from cryptography.hazmat.primitives.asymmetric import ed25519
    from google.protobuf.timestamp_pb2 import Timestamp

    from server.app.grpc._pb.fleet.v1 import reenroll_pb2
    from server.app.grpc.reenroll_servicer import ReEnrollServicer
    from server.app.grpc.reenroll_state import (
        NonceCache,
        ReEnrollRateLimiter,
        canonical_reenroll_payload,
    )
    from server.app.models.revoked_cert import RevokedCert
    from server.app.models.host import Host
    from sqlalchemy import select

    sk = ed25519.Ed25519PrivateKey.generate()
    pk_bytes = sk.public_key().public_bytes_raw()

    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=pk_bytes,
                cert_serial="OLD",
            )
        )
        await s.commit()

    nc = NonceCache(ttl_seconds=60)
    nonce = b"\x77" * 32
    nc.put("h-1", nonce)

    svc = ReEnrollServicer(
        session_factory=sm,
        nonce_cache=nc,
        rate_limiter=ReEnrollRateLimiter(),
        ca=fake_ca,
        ttl_days=7,
    )

    ts = int(time.time())
    sig = sk.sign(canonical_reenroll_payload("h-1", nonce, ts))

    ts_pb = Timestamp()
    ts_pb.FromSeconds(ts)

    req = reenroll_pb2.CompleteRequest(
        host_id="h-1",
        nonce=nonce,
        signature=sig,
        csr_pem=_csr_pem("h-1"),
        ts=ts_pb,
    )
    resp = await svc.Complete(req, _ctx())
    assert resp.cert_chain_pem

    async with sm() as s:
        host = await s.get(Host, "h-1")
        assert host.cert_serial != "OLD"
        revs = (
            await s.execute(
                select(RevokedCert).where(RevokedCert.host_id == "h-1")
            )
        ).scalars().all()
        assert any(r.serial == "OLD" and r.reason == "reenrolled" for r in revs)


@pytest.mark.asyncio
async def test_complete_rejects_consumed_nonce(sm, fake_ca):
    """Same nonce can't be used twice."""
    import time
    import grpc

    from cryptography.hazmat.primitives.asymmetric import ed25519
    from google.protobuf.timestamp_pb2 import Timestamp

    from server.app.grpc._pb.fleet.v1 import reenroll_pb2
    from server.app.grpc.reenroll_servicer import ReEnrollServicer
    from server.app.grpc.reenroll_state import (
        NonceCache,
        ReEnrollRateLimiter,
        canonical_reenroll_payload,
    )
    from server.app.models.host import Host

    sk = ed25519.Ed25519PrivateKey.generate()
    pk_bytes = sk.public_key().public_bytes_raw()

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=pk_bytes, cert_serial="OLD"))
        await s.commit()

    nc = NonceCache()
    nonce = b"\x77" * 32
    nc.put("h-1", nonce)

    svc = ReEnrollServicer(
        session_factory=sm,
        nonce_cache=nc,
        rate_limiter=ReEnrollRateLimiter(),
        ca=fake_ca,
        ttl_days=7,
    )

    ts = int(time.time())
    sig = sk.sign(canonical_reenroll_payload("h-1", nonce, ts))
    ts_pb = Timestamp()
    ts_pb.FromSeconds(ts)
    req = reenroll_pb2.CompleteRequest(
        host_id="h-1",
        nonce=nonce,
        signature=sig,
        csr_pem=_csr_pem("h-1"),
        ts=ts_pb,
    )
    await svc.Complete(req, _ctx())  # first ok

    ctx2 = _ctx()
    with pytest.raises(Exception):
        await svc.Complete(req, ctx2)
    assert ctx2.aborted_code == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_complete_rejects_skewed_ts(sm, fake_ca):
    import time
    import grpc

    from cryptography.hazmat.primitives.asymmetric import ed25519
    from google.protobuf.timestamp_pb2 import Timestamp

    from server.app.grpc._pb.fleet.v1 import reenroll_pb2
    from server.app.grpc.reenroll_servicer import ReEnrollServicer
    from server.app.grpc.reenroll_state import (
        NonceCache,
        ReEnrollRateLimiter,
        canonical_reenroll_payload,
    )
    from server.app.models.host import Host

    sk = ed25519.Ed25519PrivateKey.generate()
    pk_bytes = sk.public_key().public_bytes_raw()

    async with sm() as s:
        s.add(Host(id="h-1", hostname="h1", agent_pubkey=pk_bytes, cert_serial="OLD"))
        await s.commit()

    nc = NonceCache()
    nonce = b"\x77" * 32
    nc.put("h-1", nonce)

    svc = ReEnrollServicer(
        session_factory=sm,
        nonce_cache=nc,
        rate_limiter=ReEnrollRateLimiter(),
        ca=fake_ca,
        ttl_days=7,
    )

    ts = int(time.time()) - 120  # 2 minutes ago, > 60s window
    sig = sk.sign(canonical_reenroll_payload("h-1", nonce, ts))
    ts_pb = Timestamp()
    ts_pb.FromSeconds(ts)
    req = reenroll_pb2.CompleteRequest(
        host_id="h-1",
        nonce=nonce,
        signature=sig,
        csr_pem=_csr_pem("h-1"),
        ts=ts_pb,
    )
    ctx = _ctx()
    with pytest.raises(Exception):
        await svc.Complete(req, ctx)
    assert ctx.aborted_code == grpc.StatusCode.PERMISSION_DENIED


def _csr_pem(cn: str) -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM)
