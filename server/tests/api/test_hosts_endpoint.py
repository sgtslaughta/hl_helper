"""Tests for /v1/hosts endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

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
from server.app.models.host import Host
from server.app.revocation.service import RevocationService


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
async def client(async_session_maker, revocation_service: RevocationService, monkeypatch):
    """Create FastAPI test client with overridden dependencies."""
    from unittest import mock
    from server.app.settings.config import FleetSettings
    from pydantic import SecretStr

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
async def test_delete_host_204(client: httpx.AsyncClient, async_session_maker):
    """Test DELETE /v1/hosts/{host_id} returns 204 and marks host revoked."""
    # Pre-create host
    async with async_session_maker() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
        )
        session.add(host)
        await session.commit()

    # Delete (with admin token header)
    response = await client.delete(
        "/v1/hosts/test-host-1",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 204

    # Verify host is marked revoked
    async with async_session_maker() as session:
        refreshed = await session.get(Host, "test-host-1")
        assert refreshed.status == "revoked"


@pytest.mark.asyncio
async def test_delete_unknown_host_404(client: httpx.AsyncClient):
    """Test DELETE unknown host returns 404."""
    response = await client.delete(
        "/v1/hosts/nonexistent",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 404
    assert "not found" in response.text.lower()


@pytest.mark.asyncio
async def test_delete_already_revoked_409(client: httpx.AsyncClient, async_session_maker):
    """Test DELETE already-revoked host returns 409."""
    # Pre-create revoked host
    async with async_session_maker() as session:
        host = Host(
            id="test-host-1",
            hostname="test.example.com",
            agent_pubkey=b"x" * 32,
            cert_serial="abc123",
            status="revoked",
        )
        session.add(host)
        await session.commit()

    # Delete (with admin token header)
    response = await client.delete(
        "/v1/hosts/test-host-1",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 409
    assert "revoked" in response.text.lower()


@pytest.mark.asyncio
async def test_list_hosts_empty(client: httpx.AsyncClient):
    """Test GET /v1/hosts returns empty list when no hosts."""
    response = await client.get(
        "/v1/hosts",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_hosts_returns_all(client: httpx.AsyncClient, async_session_maker):
    """Test GET /v1/hosts returns all hosts."""
    # Pre-create hosts
    async with async_session_maker() as session:
        hosts = [
            Host(
                id="host-1",
                hostname="host1.example.com",
                agent_pubkey=b"x" * 32,
                status="online",
            ),
            Host(
                id="host-2",
                hostname="host2.example.com",
                agent_pubkey=b"y" * 32,
                status="offline",
            ),
        ]
        session.add_all(hosts)
        await session.commit()

    response = await client.get(
        "/v1/hosts",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "host-1"
    assert data[0]["hostname"] == "host1.example.com"
    assert data[0]["status"] == "online"
    assert data[1]["id"] == "host-2"
    assert data[1]["hostname"] == "host2.example.com"
    assert data[1]["status"] == "offline"


@pytest.mark.asyncio
async def test_list_hosts_filter_by_status(client: httpx.AsyncClient, async_session_maker):
    """Test GET /v1/hosts with status filter."""
    # Pre-create hosts
    async with async_session_maker() as session:
        hosts = [
            Host(
                id="host-1",
                hostname="host1.example.com",
                agent_pubkey=b"x" * 32,
                status="online",
            ),
            Host(
                id="host-2",
                hostname="host2.example.com",
                agent_pubkey=b"y" * 32,
                status="offline",
            ),
        ]
        session.add_all(hosts)
        await session.commit()

    response = await client.get(
        "/v1/hosts?state=online",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "host-1"
    assert data[0]["status"] == "online"
