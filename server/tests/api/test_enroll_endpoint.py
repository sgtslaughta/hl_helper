"""Tests for /v1/enroll endpoint."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.enrollment.service import EnrollmentService
from server.app.models.base import Base


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


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    """Create in-memory aiosqlite database with tables."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def ca(tmp_path: Path) -> InternalCA:
    """Bootstrap CA for testing."""
    return InternalCA.bootstrap(tmp_path / "ca")


@pytest.fixture
def signing_backend(tmp_path: Path) -> FileBackend:
    """Bootstrap signing backend for testing."""
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest.fixture
def enrollment_service(ca: InternalCA, signing_backend: FileBackend) -> EnrollmentService:
    """Create enrollment service."""
    return EnrollmentService(
        ca=ca,
        signing_backend=signing_backend,
        grpc_endpoint="grpc://localhost:50051",
        cert_ttl=timedelta(hours=24),
    )


@pytest.fixture
async def client(async_session_maker, enrollment_service: EnrollmentService):
    """Create FastAPI test client with overridden dependencies."""
    from server.app.api.v1.enroll import get_enrollment_service, get_session

    app = create_app()

    async def override_session_dep() -> AsyncIterator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    def override_service_dep() -> EnrollmentService:
        return enrollment_service

    # Override the dependency functions
    app.dependency_overrides[get_session] = override_session_dep
    app.dependency_overrides[get_enrollment_service] = override_service_dep

    # Mock the rate limiter check to always pass
    with mock.patch("server.app.api.middleware.rate_limit.RateLimiter.check", return_value=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_enroll_endpoint_happy_path(
    client: httpx.AsyncClient,
    enrollment_service: EnrollmentService,
    async_session_maker,
) -> None:
    """Test successful enrollment."""
    csr_pem, agent_pubkey = make_csr()
    agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")

    # Issue token
    async with async_session_maker() as session:
        plaintext, _ = await enrollment_service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

    # POST to endpoint
    response = await client.post(
        "/v1/enroll",
        json={
            "token": plaintext,
            "hostname": "test-agent",
            "csr_pem": csr_pem.decode("utf-8"),
            "agent_pubkey_b64": agent_pubkey_b64,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "host_id" in data
    assert "leaf_cert_pem" in data
    assert "intermediate_cert_pem" in data
    assert "root_cert_pem" in data
    assert "server_signing_pubkey_b64" in data
    assert "grpc_endpoint" in data

    # Verify base64 pubkey decodes to 32 bytes
    pubkey_decoded = base64.b64decode(data["server_signing_pubkey_b64"])
    assert len(pubkey_decoded) == 32


@pytest.mark.asyncio
async def test_enroll_endpoint_unknown_token(
    client: httpx.AsyncClient,
) -> None:
    """Test unknown token returns 401 with standard error body."""
    csr_pem, agent_pubkey = make_csr()
    agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")

    response = await client.post(
        "/v1/enroll",
        json={
            "token": "unknown-token-xxx-which-is-long-enough",
            "hostname": "test-agent",
            "csr_pem": csr_pem.decode("utf-8"),
            "agent_pubkey_b64": agent_pubkey_b64,
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert data.get("title") == "invalid_or_expired_token"
    assert data.get("status") == 401


@pytest.mark.asyncio
async def test_enroll_endpoint_expired_token(
    client: httpx.AsyncClient,
    enrollment_service: EnrollmentService,
    async_session_maker,
) -> None:
    """Test expired token returns 401 with standard error body."""
    csr_pem, agent_pubkey = make_csr()
    agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")
    now = datetime.now(timezone.utc)

    # Issue expired token
    async with async_session_maker() as session:
        plaintext, _ = await enrollment_service.issue_token(
            session,
            issued_by="admin@test",
            ttl=timedelta(minutes=15),
            now=now - timedelta(minutes=20),
        )
        await session.commit()

    response = await client.post(
        "/v1/enroll",
        json={
            "token": plaintext,
            "hostname": "test-agent",
            "csr_pem": csr_pem.decode("utf-8"),
            "agent_pubkey_b64": agent_pubkey_b64,
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert data.get("title") == "invalid_or_expired_token"
    assert data.get("status") == 401


@pytest.mark.asyncio
async def test_enroll_endpoint_already_redeemed(
    client: httpx.AsyncClient,
    enrollment_service: EnrollmentService,
    async_session_maker,
) -> None:
    """Test already-redeemed token returns 401 with standard error body."""
    csr_pem, agent_pubkey = make_csr()

    # Issue and redeem once
    async with async_session_maker() as session:
        plaintext, _ = await enrollment_service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

        await enrollment_service.redeem(
            session,
            token_plaintext=plaintext,
            csr_pem=csr_pem,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        await session.commit()

    # Try to redeem again
    csr_pem2, agent_pubkey2 = make_csr()
    agent_pubkey_b64_2 = base64.b64encode(agent_pubkey2).decode("ascii")

    response = await client.post(
        "/v1/enroll",
        json={
            "token": plaintext,
            "hostname": "test-agent-2",
            "csr_pem": csr_pem2.decode("utf-8"),
            "agent_pubkey_b64": agent_pubkey_b64_2,
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert data.get("title") == "invalid_or_expired_token"
    assert data.get("status") == 401


@pytest.mark.asyncio
async def test_enroll_endpoint_all_token_failures_uniform(
    client: httpx.AsyncClient,
    enrollment_service: EnrollmentService,
    async_session_maker,
) -> None:
    """Test that unknown, expired, and already-redeemed tokens all return same response body."""
    csr_pem, agent_pubkey = make_csr()
    agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")
    now = datetime.now(timezone.utc)

    # Prepare: unknown, expired, and already-redeemed tokens
    async with async_session_maker() as session:
        # Expired token
        expired_token, _ = await enrollment_service.issue_token(
            session,
            issued_by="admin@test",
            ttl=timedelta(minutes=15),
            now=now - timedelta(minutes=20),
        )
        # Already-redeemed token
        redeemed_token, _ = await enrollment_service.issue_token(
            session,
            issued_by="admin@test",
            ttl=timedelta(minutes=15),
        )
        await session.commit()

        await enrollment_service.redeem(
            session,
            token_plaintext=redeemed_token,
            csr_pem=csr_pem,
            hostname="test-host",
            agent_pubkey=agent_pubkey,
        )
        await session.commit()

    unknown_token = "unknown-token-xxx-which-is-long-enough"

    # All three should return the same response
    for token in [unknown_token, expired_token, redeemed_token]:
        response = await client.post(
            "/v1/enroll",
            json={
                "token": token,
                "hostname": "test-agent",
                "csr_pem": csr_pem.decode("utf-8"),
                "agent_pubkey_b64": agent_pubkey_b64,
            },
        )
        assert response.status_code == 401
        data = response.json()
        assert data.get("title") == "invalid_or_expired_token"
        assert data.get("status") == 401


@pytest.mark.asyncio
async def test_enroll_endpoint_bad_csr(
    client: httpx.AsyncClient,
    enrollment_service: EnrollmentService,
    async_session_maker,
) -> None:
    """Test bad CSR returns 400."""
    agent_pubkey = b"x" * 32
    agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")

    # Issue token
    async with async_session_maker() as session:
        plaintext, _ = await enrollment_service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

    response = await client.post(
        "/v1/enroll",
        json={
            "token": plaintext,
            "hostname": "test-agent",
            "csr_pem": "not a csr",
            "agent_pubkey_b64": agent_pubkey_b64,
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_enroll_endpoint_bad_pubkey_b64(
    client: httpx.AsyncClient,
    enrollment_service: EnrollmentService,
    async_session_maker,
) -> None:
    """Test bad base64 pubkey returns 400."""
    csr_pem, _ = make_csr()

    # Issue token
    async with async_session_maker() as session:
        plaintext, _ = await enrollment_service.issue_token(
            session, issued_by="admin@test", ttl=timedelta(minutes=15)
        )
        await session.commit()

    response = await client.post(
        "/v1/enroll",
        json={
            "token": plaintext,
            "hostname": "test-agent",
            "csr_pem": csr_pem.decode("utf-8"),
            "agent_pubkey_b64": "not valid base64!!!",
        },
    )

    assert response.status_code == 400
