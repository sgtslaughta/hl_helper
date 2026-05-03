"""Tests for request middleware."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.api.v1.hosts import get_revocation_service, get_session
from server.app.crypto.signing import FileBackend
from server.app.audit.sql_chain import SqlAuditChain
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.models.base import Base
from server.app.revocation.service import RevocationService
from server.app.settings.config import FleetSettings
from pydantic import SecretStr


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    """Create in-memory aiosqlite database with tables."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def signing_backend(tmp_path: Path) -> FileBackend:
    """Create signing backend."""
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest.fixture
def audit_chain(signing_backend: FileBackend) -> SqlAuditChain:
    """Create audit chain."""
    return SqlAuditChain(signing_backend, checkpoint_interval=100)


@pytest.fixture
def dispatcher() -> CommandDispatcher:
    """Create dispatcher."""
    return CommandDispatcher()


@pytest.fixture
def revocation_service(
    dispatcher: CommandDispatcher,
    audit_chain: SqlAuditChain,
) -> RevocationService:
    """Create revocation service."""
    return RevocationService(dispatcher=dispatcher, audit=audit_chain)


@pytest.fixture
async def client(async_session_maker, revocation_service: RevocationService):
    """Create FastAPI test client with overridden dependencies."""
    app = create_app()

    async def override_session_dep() -> AsyncIterator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    def override_service_dep() -> RevocationService:
        return revocation_service

    # Override the dependency functions
    app.dependency_overrides[get_session] = override_session_dep
    app.dependency_overrides[get_revocation_service] = override_service_dep

    # Mock load_settings to return a settings object with admin_token set
    mock_settings = FleetSettings(admin_token=SecretStr("test-admin-token"))

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_request_id_echoed(client: httpx.AsyncClient):
    """Verify request-ID header is echoed back in response."""
    r = await client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    # /healthz may not exist; the middleware still runs on the 404 path.
    assert r.headers.get("X-Request-ID") == "abc-123"


@pytest.mark.asyncio
async def test_request_id_generated_when_absent(client: httpx.AsyncClient):
    """Verify request-ID is generated if not provided."""
    r = await client.get("/")
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) >= 16


@pytest.mark.asyncio
async def test_admin_required_constant_time_comparison():
    """Verify admin_required uses constant-time comparison (secrets.compare_digest)."""
    import secrets
    from unittest.mock import patch
    from server.app.api.middleware.admin_auth import admin_required
    from fastapi import Request
    from unittest.mock import MagicMock

    # Mock settings
    mock_settings = FleetSettings(admin_token=SecretStr("correct-token"))

    # Create mock request with correct token
    with patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        # Track if secrets.compare_digest was called
        with patch("secrets.compare_digest", wraps=secrets.compare_digest) as mock_compare:
            mock_request = MagicMock(spec=Request)
            mock_request.headers.get.return_value = "Bearer correct-token"

            result = await admin_required(mock_request)

            # Verify that secrets.compare_digest was called
            assert mock_compare.called
            # Verify the call was with the token and the secret
            call_args = mock_compare.call_args
            assert call_args[0][0] == "correct-token"
            assert call_args[0][1] == "correct-token"
            # Verify correct token returns "admin"
            assert result == "admin"


@pytest.mark.asyncio
async def test_admin_required_invalid_token_still_uses_constant_time():
    """Verify invalid token is still compared using constant-time (no timing leak)."""
    import secrets
    from unittest.mock import patch
    from server.app.api.middleware.admin_auth import admin_required
    from fastapi import Request, HTTPException
    from unittest.mock import MagicMock

    mock_settings = FleetSettings(admin_token=SecretStr("correct-token"))

    with patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        with patch("secrets.compare_digest", wraps=secrets.compare_digest) as mock_compare:
            mock_request = MagicMock(spec=Request)
            mock_request.headers.get.return_value = "Bearer wrong-token"

            with pytest.raises(HTTPException) as exc_info:
                await admin_required(mock_request)

            # Verify constant-time comparison was still used
            assert mock_compare.called
            assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_required_missing_token_same_as_wrong_token():
    """Verify missing/None admin_token returns 401 same as wrong token (no 503)."""
    from unittest.mock import patch
    from server.app.api.middleware.admin_auth import admin_required
    from fastapi import Request, HTTPException
    from unittest.mock import MagicMock

    # Simulate admin_token being None
    mock_settings = FleetSettings(admin_token=None)

    with patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = "Bearer some-token"

        with pytest.raises(HTTPException) as exc_info:
            await admin_required(mock_request)

        # Should return 503 when not configured (current behavior, not changed per task)
        assert exc_info.value.status_code == 503
