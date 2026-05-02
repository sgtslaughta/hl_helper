"""Tests for server.app.enrollment.service.EnrollmentService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.enrollment.service import (
    CsrInvalidError,
    EnrollmentService,
    TokenAlreadyRedeemedError,
    TokenExpiredError,
    TokenNotFoundError,
)
from server.app.models.base import Base
from server.app.models.enrollment_token import EnrollmentToken
from server.app.models.host import Host


@pytest.fixture
async def async_session(tmp_path: Path):
    """Create in-memory aiosqlite database with tables."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def get_session() -> AsyncSession:
        async with sm() as session:
            yield session

    return sm


@pytest.fixture
def ca(tmp_path: Path) -> InternalCA:
    """Bootstrap CA for testing."""
    return InternalCA.bootstrap(tmp_path / "ca")


@pytest.fixture
def signing_backend(tmp_path: Path) -> FileBackend:
    """Bootstrap signing backend for testing."""
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest.fixture
def service(ca: InternalCA, signing_backend: FileBackend) -> EnrollmentService:
    """Create enrollment service."""
    return EnrollmentService(
        ca=ca,
        signing_backend=signing_backend,
        grpc_endpoint="grpc://localhost:50051",
        cert_ttl=timedelta(hours=24),
    )


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
async def test_issue_token_persists_hash_only(
    service: EnrollmentService, async_session
) -> None:
    """Verify issue_token returns plaintext but persists only hash."""
    async with async_session() as session:
        plaintext, token_row = await service.issue_token(
            session,
            issued_by="admin@test",
            ttl=timedelta(minutes=15),
            note="test token",
        )
        await session.commit()

        # Plaintext should be non-empty
        assert plaintext
        assert len(plaintext) >= 20

        # Token should be queryable by hash
        from server.app.enrollment.tokens import hash_token

        expected_hash = hash_token(plaintext)
        assert token_row.token_hash == expected_hash

        # redeemed_at should be None
        assert token_row.redeemed_at is None
        assert token_row.redeemed_host_id is None


@pytest.mark.asyncio
async def test_issue_token_unique_hashes(
    service: EnrollmentService, async_session
) -> None:
    """Verify all issued tokens have unique hashes."""
    async with async_session() as session:
        hashes = set()
        for _ in range(5):
            plaintext, token_row = await service.issue_token(
                session, issued_by="admin@test", ttl=timedelta(minutes=15)
            )
            await session.commit()
            hashes.add(bytes(token_row.token_hash))

        assert len(hashes) == 5


@pytest.mark.asyncio
async def test_redeem_happy_path(
    service: EnrollmentService, async_session
) -> None:
    """Test successful token redemption."""
    csr_pem, agent_pubkey = make_csr()

    async with async_session() as session:
        # Issue token
        plaintext, _ = await service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

        # Redeem token
        result = await service.redeem(
            session,
            token_plaintext=plaintext,
            csr_pem=csr_pem,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        await session.commit()

        # Verify result
        assert result.host_id
        assert result.leaf_cert_pem
        assert result.intermediate_cert_pem
        assert result.root_cert_pem
        assert len(result.server_signing_pubkey) == 32
        assert result.grpc_endpoint == "grpc://localhost:50051"

        # Verify certificates parse
        x509.load_pem_x509_certificate(result.leaf_cert_pem)
        x509.load_pem_x509_certificate(result.intermediate_cert_pem)
        x509.load_pem_x509_certificate(result.root_cert_pem)

        # Verify Host row exists
        host = await session.get(Host, result.host_id)
        assert host
        assert host.hostname == "test-host"
        assert host.agent_pubkey == agent_pubkey
        assert host.enrolled_at is not None
        assert host.status == "offline"
        assert host.labels == {}

        # Verify token is marked redeemed
        token = await session.get(EnrollmentToken, _.id)
        assert token
        assert token.redeemed_at is not None
        assert token.redeemed_host_id == result.host_id


@pytest.mark.asyncio
async def test_redeem_unknown_token_raises_not_found(
    service: EnrollmentService, async_session
) -> None:
    """Test redeem with unknown token."""
    csr_pem, agent_pubkey = make_csr()

    async with async_session() as session:
        with pytest.raises(TokenNotFoundError):
            await service.redeem(
                session,
                token_plaintext="unknown-token-xxx",
                csr_pem=csr_pem,
                hostname="test-host",
                agent_pubkey=agent_pubkey,
            )


@pytest.mark.asyncio
async def test_redeem_expired_token_raises(
    service: EnrollmentService, async_session
) -> None:
    """Test redeem with expired token."""
    csr_pem, agent_pubkey = make_csr()
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        # Issue token with past expiry
        plaintext, token_row = await service.issue_token(
            session,
            issued_by="admin@test",
            ttl=timedelta(minutes=15),
            now=now - timedelta(minutes=20),  # Expired
        )
        await session.commit()

        with pytest.raises(TokenExpiredError):
            await service.redeem(
                session,
                token_plaintext=plaintext,
                csr_pem=csr_pem,
                hostname="test-host",
                agent_pubkey=agent_pubkey,
                now=now,
            )


@pytest.mark.asyncio
async def test_redeem_replay_rejects(
    service: EnrollmentService, async_session
) -> None:
    """Test replay protection: second redeem rejects."""
    csr_pem, agent_pubkey = make_csr()

    async with async_session() as session:
        plaintext, _ = await service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

        # First redeem succeeds
        result = await service.redeem(
            session,
            token_plaintext=plaintext,
            csr_pem=csr_pem,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        await session.commit()
        assert result.host_id

        # Second redeem fails
        csr_pem2, agent_pubkey2 = make_csr()
        with pytest.raises(TokenAlreadyRedeemedError):
            await service.redeem(
                session,
                token_plaintext=plaintext,
                csr_pem=csr_pem2,
                hostname="test-host-2",
                agent_pubkey=agent_pubkey2,
            )


@pytest.mark.asyncio
async def test_redeem_invalid_csr_raises_and_no_side_effects(
    service: EnrollmentService, async_session
) -> None:
    """Test invalid CSR raises CsrInvalidError without marking token redeemed."""
    agent_pubkey = b"x" * 32

    async with async_session() as session:
        plaintext, token_row = await service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

        # Try to redeem with invalid CSR
        with pytest.raises(CsrInvalidError):
            await service.redeem(
                session,
                token_plaintext=plaintext,
                csr_pem=b"not a csr",
                hostname="test-host",
                agent_pubkey=agent_pubkey,
            )

        # Token should NOT be marked redeemed
        token = await session.get(EnrollmentToken, token_row.id)
        assert token
        assert token.redeemed_at is None
        assert token.redeemed_host_id is None


@pytest.mark.asyncio
async def test_redeem_concurrent_calls_only_one_wins(
    service: EnrollmentService, async_session
) -> None:
    """Two concurrent redeem() calls on same token: exactly one succeeds, other raises TokenAlreadyRedeemedError."""
    import asyncio

    csr_pem1, agent_pubkey1 = make_csr()
    csr_pem2, agent_pubkey2 = make_csr()

    async with async_session() as session:
        plaintext, _ = await service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

    # Run two concurrent redeem calls using separate sessions
    async def redeem_task(csr_pem: bytes, agent_pubkey: bytes):
        async with async_session() as session:
            try:
                result = await service.redeem(
                    session,
                    token_plaintext=plaintext,
                    csr_pem=csr_pem,
                    hostname="test-host",
                    agent_pubkey=agent_pubkey,
                )
                await session.commit()
                return ("success", result)
            except TokenAlreadyRedeemedError:
                return ("already_redeemed", None)
            except Exception as e:
                return ("error", str(e))

    results = await asyncio.gather(
        redeem_task(csr_pem1, agent_pubkey1),
        redeem_task(csr_pem2, agent_pubkey2),
    )

    # Exactly one should succeed, one should fail with TokenAlreadyRedeemedError
    outcomes = [r[0] for r in results]
    assert outcomes.count("success") == 1
    assert outcomes.count("already_redeemed") == 1
