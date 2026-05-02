"""Tests for RFC 9457 problem+JSON error handler."""

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
async def test_404_returns_problem_json(client: httpx.AsyncClient):
    """Verify 404 returns RFC 9457 problem+JSON response."""
    r = await client.get("/nonexistent")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    assert body["type"].startswith("/errors/")
    assert body["instance"] == "/nonexistent"
    assert "trace_id" in body
