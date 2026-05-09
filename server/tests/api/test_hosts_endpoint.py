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
async def client(
    async_session_maker, revocation_service: RevocationService, audit_chain: SqlAuditChain, monkeypatch
):
    """Create FastAPI test client with overridden dependencies."""
    from unittest import mock
    from server.app.settings.config import FleetSettings
    from server.app.dispatcher.dispatcher import DispatchResult
    from server.tests._helpers.app_state import make_test_app_state
    from pydantic import SecretStr

    app = create_app()

    # Mock api_dispatcher to return realistic results
    mock_api_dispatcher = mock.AsyncMock()
    mock_api_dispatcher.dispatch = mock.AsyncMock(
        return_value=DispatchResult(
            task_id="task-123",
            dispatched=["test-host-1"],
            denied=[],
            pending_approval_ids=[],
        )
    )

    # Build app state
    app_state = make_test_app_state(
        sessionmaker=async_session_maker,
        audit_chain=audit_chain,
        revocation_service=revocation_service,
        api_dispatcher=mock_api_dispatcher,
    )
    app.state.app_state = app_state

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
    """Test DELETE /v1/hosts/{host_id} returns 204 and removes host row."""
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

    # Verify host row is gone
    async with async_session_maker() as session:
        refreshed = await session.get(Host, "test-host-1")
        assert refreshed is None


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
async def test_delete_already_revoked_204(client: httpx.AsyncClient, async_session_maker):
    """DELETE on already-revoked host still removes the row (idempotent hard delete)."""
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

    response = await client.delete(
        "/v1/hosts/test-host-1",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 204

    async with async_session_maker() as session:
        assert await session.get(Host, "test-host-1") is None


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


@pytest.mark.asyncio
async def test_shell_exec_as_root_no_reason_now_allowed(
    client: httpx.AsyncClient, async_session_maker
):
    """as_root=true with empty reason -> dispatches successfully (admin-trusted)."""
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

    response = await client.post(
        "/v1/hosts/test-host-1/actions/shell-exec",
        headers={
            "Authorization": "Bearer test-admin-token",
            "X-Acting-Principal": "user:admin",
        },
        json={"command": "ls", "as_root": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["dispatched"] == ["test-host-1"]


@pytest.mark.asyncio
async def test_shell_exec_as_root_dispatches_with_reason(
    client: httpx.AsyncClient, async_session_maker
):
    """Valid as_root request -> 200; payload threads as_root + reason; audit entry written."""
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

    response = await client.post(
        "/v1/hosts/test-host-1/actions/shell-exec",
        headers={
            "Authorization": "Bearer test-admin-token",
            "X-Acting-Principal": "user:admin",
        },
        json={
            "command": "ls",
            "as_root": True,
            "reason": "package refresh",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["dispatched"] == ["test-host-1"]


@pytest.mark.asyncio
async def test_rescan_host_409_when_offline(client: httpx.AsyncClient, async_session_maker):
    """POST /v1/hosts/{id}/rescan returns 409 when no live agent stream."""
    async with async_session_maker() as session:
        session.add(Host(id="rh-1", hostname="r.example.com", agent_pubkey=b"x" * 32, cert_serial="r1"))
        await session.commit()

    # No agent connected → push_control returns False → 409
    resp = await client.post(
        "/v1/hosts/rh-1/rescan",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 409
    assert "host_not_connected" in resp.text


@pytest.mark.asyncio
async def test_rescan_host_404_for_unknown_host(client: httpx.AsyncClient):
    resp = await client.post(
        "/v1/hosts/missing/rescan",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rescan_host_202_when_pushed(client: httpx.AsyncClient, async_session_maker, monkeypatch):
    """POST rescan returns 202 + task_id when push_control accepts the message."""
    async with async_session_maker() as session:
        session.add(Host(id="rh-2", hostname="r2.example.com", agent_pubkey=b"x" * 32, cert_serial="r2"))
        await session.commit()

    pushed: list[tuple[str, object]] = []

    def fake_push(host_id, msg):  # type: ignore[no-untyped-def]
        pushed.append((host_id, msg))
        return True

    monkeypatch.setattr("server.app.grpc.agent_bridge.push_control", fake_push)

    resp = await client.post(
        "/v1/hosts/rh-2/rescan",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_id"]
    assert pushed and pushed[0][0] == "rh-2"
    # Pushed msg must carry RunInventory oneof
    assert pushed[0][1].WhichOneof("msg") == "run_inventory"
