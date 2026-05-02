"""Threat-model E2E tests for TLS enrollment (Phase 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import grpc
import grpc.aio
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2_grpc
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.enrollment.service import (
    EnrollmentService,
    TokenAlreadyRedeemedError,
    TokenExpiredError,
)
from server.app.models.base import Base
from server.app.db.session import make_engine, make_sessionmaker


def make_csr() -> tuple[bytes, bytes]:
    """Build a fresh Ed25519 keypair + CSR. Returns (csr_pem, raw_pubkey_bytes)."""
    sk = ed25519.Ed25519PrivateKey.generate()
    pk_raw = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "agent")]))
        .sign(sk, None)
    )
    return csr.public_bytes(serialization.Encoding.PEM), pk_raw


@pytest.mark.asyncio
async def test_wrong_ca_cert_handshake_fails(
    tls_creds, grpc_server_and_dispatcher, tmp_path: Path
) -> None:
    """Verify TLS handshake fails when client cert is from wrong CA."""
    bound_addr, _ = grpc_server_and_dispatcher
    port = int(bound_addr.rsplit(":", 1)[1])
    other_ca = InternalCA.bootstrap(tmp_path / "ca2")
    wrong_cert = other_ca.issue_host_cert(make_csr()[0], host_id="h", ttl=timedelta(hours=1))
    wrong_chain = other_ca.root_cert.public_bytes(serialization.Encoding.PEM) + \
                  other_ca.int_cert.public_bytes(serialization.Encoding.PEM)
    creds = grpc.ssl_channel_credentials(root_certificates=wrong_chain,
                                          private_key=b"fake", certificate_chain=wrong_cert)
    async with grpc.aio.secure_channel(f"127.0.0.1:{port}", creds,
                options=[("grpc.ssl_target_name_override", "localhost")]) as ch:
        stub = agent_bridge_pb2_grpc.AgentBridgeStub(ch)
        call = stub.Stream(iter([]))
        with pytest.raises(grpc.aio.AioRpcError):
            await call.read()


@pytest.mark.asyncio
async def test_bootstrap_token_reuse_410(tmp_path: Path) -> None:
    """Verify token reuse fails with TokenAlreadyRedeemedError."""
    ca = InternalCA.bootstrap(tmp_path / "ca")
    service = EnrollmentService(ca, FileBackend.bootstrap(tmp_path / "sig"),
                                grpc_endpoint="grpc://localhost:50051",
                                cert_ttl=timedelta(hours=24))
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)
    csr_pem, agent_pubkey = make_csr()
    async with sm() as session:
        plaintext, _ = await service.issue_token(session, issued_by="admin@test",
                                                  ttl=timedelta(minutes=15))
        await session.commit()
        await service.redeem(session, token_plaintext=plaintext, csr_pem=csr_pem,
                            hostname="test-host", agent_pubkey=agent_pubkey)
        await session.commit()
        with pytest.raises(TokenAlreadyRedeemedError):
            await service.redeem(session, token_plaintext=plaintext,
                                csr_pem=make_csr()[0], hostname="test-host-2",
                                agent_pubkey=make_csr()[1])
    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_token_expired_410(tmp_path: Path) -> None:
    """Verify expired token fails with TokenExpiredError."""
    ca = InternalCA.bootstrap(tmp_path / "ca")
    service = EnrollmentService(ca, FileBackend.bootstrap(tmp_path / "sig"),
                                grpc_endpoint="grpc://localhost:50051",
                                cert_ttl=timedelta(hours=24))
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)
    now = datetime.now(timezone.utc)
    csr_pem, agent_pubkey = make_csr()
    async with sm() as session:
        plaintext, _ = await service.issue_token(session, issued_by="admin@test",
                                                  ttl=timedelta(minutes=15),
                                                  now=now - timedelta(minutes=20))
        await session.commit()
        with pytest.raises(TokenExpiredError):
            await service.redeem(session, token_plaintext=plaintext, csr_pem=csr_pem,
                                hostname="test-host", agent_pubkey=agent_pubkey, now=now)
    await engine.dispose()
