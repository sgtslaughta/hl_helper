"""Tests for rate limiting."""

from __future__ import annotations

import base64
import time
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.middleware.rate_limit import RateLimiter, rate_limit_dependency
from server.app.api.app import create_app
from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.enrollment.service import EnrollmentService
from server.app.models.base import Base


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_limiter_allows_burst(self) -> None:
        """Verify burst capacity allows initial requests."""
        limiter = RateLimiter(rate_per_sec=1.0, burst=3)
        now = time.time()

        # First 3 requests should succeed
        for _ in range(3):
            limiter.check("key1", now=now)

        # 4th request should fail
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("key1", now=now)
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_limiter_refills(self) -> None:
        """Verify tokens refill over time."""
        limiter = RateLimiter(rate_per_sec=1.0, burst=3)
        now = time.time()

        # Exhaust burst
        for _ in range(3):
            limiter.check("key1", now=now)

        # Should fail immediately
        with pytest.raises(HTTPException):
            limiter.check("key1", now=now)

        # Advance time by 2 seconds (should gain 2 tokens)
        now_later = now + 2.0
        limiter.check("key1", now=now_later)  # Use 1 token
        limiter.check("key1", now=now_later)  # Use 1 token

        # Should fail on 3rd request at same time
        with pytest.raises(HTTPException):
            limiter.check("key1", now=now_later)

    def test_limiter_per_key_isolation(self) -> None:
        """Verify different keys have separate buckets."""
        limiter = RateLimiter(rate_per_sec=1.0, burst=2)
        now = time.time()

        # Exhaust key1
        limiter.check("key1", now=now)
        limiter.check("key1", now=now)

        # key2 should still have capacity
        limiter.check("key2", now=now)
        limiter.check("key2", now=now)

    def test_limiter_under_rate_always_passes(self) -> None:
        """Verify requests under rate limit always pass."""
        limiter = RateLimiter(rate_per_sec=10.0, burst=100)
        now = time.time()

        # Make 50 requests spaced 0.05s apart (5 per second, under 10/sec limit)
        for i in range(50):
            current_time = now + (i * 0.05)
            limiter.check("key1", now=current_time)


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
    """Create aiosqlite database with tables."""
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
async def client_with_rate_limit(async_session_maker, enrollment_service: EnrollmentService):
    """Create FastAPI test client with rate limit applied."""
    from server.app.api.v1.enroll import get_enrollment_service, get_session
    from server.app.api.v1 import enroll

    app = create_app()

    # Create a rate limiter for testing (1 request per second, burst of 2)
    rate_limiter = RateLimiter(rate_per_sec=1.0, burst=2)

    app.dependency_overrides[get_session] = override_session_dep(async_session_maker)
    app.dependency_overrides[get_enrollment_service] = lambda: enrollment_service

    # Override the route to include rate limit dependency
    original_router = enroll.router
    # Find the enroll endpoint and re-register it with rate limit
    for route in original_router.routes:
        if hasattr(route, "path") and route.path == "/v1/enroll":
            # This is our enroll endpoint
            route.dependencies.append(Depends(rate_limit_dependency(rate_limiter)))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, rate_limiter


def override_session_dep(async_session_maker):
    """Create session dependency override."""

    async def override_session_dep_inner() -> AsyncIterator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    return override_session_dep_inner


@pytest.mark.asyncio
async def test_enroll_endpoint_under_limit_passes(
    async_session_maker,
    enrollment_service: EnrollmentService,
) -> None:
    """Test that requests under rate limit succeed."""
    from server.app.api.v1.enroll import get_enrollment_service, get_session

    app = create_app()
    rate_limiter = RateLimiter(rate_per_sec=0.5, burst=5)  # Very generous: 1 per 2s, burst 5

    # Override dependencies
    app.dependency_overrides[get_session] = override_session_dep(async_session_maker)
    app.dependency_overrides[get_enrollment_service] = lambda: enrollment_service

    # Manually patch the endpoint's dependencies
    for route in app.router.routes:
        if hasattr(route, "path") and route.path == "/v1/enroll":
            route.dependencies.append(Depends(rate_limit_dependency(rate_limiter)))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Issue 5 tokens and make 5 requests quickly
        tokens = []
        async with async_session_maker() as session:
            for _ in range(5):
                plaintext, _ = await enrollment_service.issue_token(
                    session, issued_by="admin@test", ttl=timedelta(minutes=15)
                )
                tokens.append(plaintext)
                await session.commit()

        csr_pem, agent_pubkey = make_csr()
        agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")

        # Make 5 requests - all should succeed due to burst=5
        success_count = 0
        for token in tokens:
            response = await client.post(
                "/v1/enroll",
                json={
                    "token": token,
                    "hostname": "test-agent",
                    "csr_pem": csr_pem.decode("utf-8"),
                    "agent_pubkey_b64": agent_pubkey_b64,
                },
            )
            if response.status_code == 200:
                success_count += 1

        assert success_count == 5


@pytest.mark.asyncio
async def test_enroll_endpoint_over_limit_returns_429(
    async_session_maker,
    enrollment_service: EnrollmentService,
) -> None:
    """Test that requests over rate limit return 429."""
    from server.app.api.v1.enroll import get_enrollment_service, get_session
    from fastapi import Depends

    app = create_app()
    rate_limiter = RateLimiter(rate_per_sec=10.0, burst=2)  # Tight: burst of 2
    from server.app.api.middleware.rate_limit import rate_limit_dependency

    # Override dependencies
    app.dependency_overrides[get_session] = override_session_dep(async_session_maker)
    app.dependency_overrides[get_enrollment_service] = lambda: enrollment_service

    # Patch the endpoint
    for route in app.router.routes:
        if hasattr(route, "path") and route.path == "/v1/enroll":
            route.dependencies.append(Depends(rate_limit_dependency(rate_limiter)))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Issue 10 tokens
        tokens = []
        async with async_session_maker() as session:
            for _ in range(10):
                plaintext, _ = await enrollment_service.issue_token(
                    session, issued_by="admin@test", ttl=timedelta(minutes=15)
                )
                tokens.append(plaintext)
                await session.commit()

        csr_pem, agent_pubkey = make_csr()
        agent_pubkey_b64 = base64.b64encode(agent_pubkey).decode("ascii")

        # Make 10 requests - first 2 should succeed, rest should get 429
        status_codes = []
        for token in tokens:
            response = await client.post(
                "/v1/enroll",
                json={
                    "token": token,
                    "hostname": "test-agent",
                    "csr_pem": csr_pem.decode("utf-8"),
                    "agent_pubkey_b64": agent_pubkey_b64,
                },
            )
            status_codes.append(response.status_code)

        # First 2 should be 200 (success) or 409 (already redeemed, not rate limited)
        # The rest should be 429 (rate limited)
        assert status_codes[0] in [200, 409]
        assert status_codes[1] in [200, 409]
        # After burst is exhausted, we should get 429s
        assert 429 in status_codes[2:]
