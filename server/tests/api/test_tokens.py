"""Tests for /v1/tokens API endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest import mock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.auth.api_key import ApiKeyService
from server.app.models.base import Base
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state
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
async def client(async_session_maker):
    """Create FastAPI test client with test database."""
    app = create_app()

    async def override_session_dep() -> AsyncIterator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    # This is a bit of a hack, but we need to override the sessionmaker
    # that the routes use. We'll store it in app.state.
    app.state.app_state = make_test_app_state(sessionmaker=async_session_maker)

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
async def test_issue_token_201(client: httpx.AsyncClient, async_session_maker):
    """POST /v1/tokens with admin bearer returns 201 with plaintext."""
    response = await client.post(
        "/v1/tokens",
        json={
            "principal_id": "user-123",
            "principal_kind": "user",
            "name": "my-api-key",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "plaintext" in data
    assert "api_key_id" in data
    assert "prefix" in data
    assert "last_4" in data
    assert data["plaintext"].startswith("hlk_")
    assert data["prefix"] == data["plaintext"][:8]
    assert data["last_4"] == data["plaintext"][-4:]


@pytest.mark.asyncio
async def test_issue_token_without_bearer_401(client: httpx.AsyncClient):
    """POST /v1/tokens without admin bearer returns 401."""
    response = await client.post(
        "/v1/tokens",
        json={
            "principal_id": "user-123",
            "principal_kind": "user",
            "name": "my-api-key",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_issue_token_with_wrong_bearer_401(client: httpx.AsyncClient):
    """POST /v1/tokens with wrong bearer token returns 401."""
    response = await client.post(
        "/v1/tokens",
        json={
            "principal_id": "user-123",
            "principal_kind": "user",
            "name": "my-api-key",
        },
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_tokens_200(client: httpx.AsyncClient, async_session_maker):
    """GET /v1/tokens with admin bearer returns list of tokens."""
    # Create a token first
    response = await client.post(
        "/v1/tokens",
        json={
            "principal_id": "user-123",
            "principal_kind": "user",
            "name": "my-api-key",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 201
    created_id = response.json()["api_key_id"]

    # List tokens
    response = await client.get(
        "/v1/tokens",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Find our created token
    token = next((t for t in data if t["id"] == created_id), None)
    assert token is not None
    assert token["principal_id"] == "user-123"
    assert token["principal_kind"] == "user"
    assert token["name"] == "my-api-key"
    # plaintext should NOT be in the list response
    assert "plaintext" not in token


@pytest.mark.asyncio
async def test_list_tokens_without_bearer_401(client: httpx.AsyncClient):
    """GET /v1/tokens without admin bearer returns 401."""
    response = await client.get("/v1/tokens")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoke_token_204(client: httpx.AsyncClient, async_session_maker):
    """DELETE /v1/tokens/{id} with admin bearer returns 204."""
    # Create a token first
    response = await client.post(
        "/v1/tokens",
        json={
            "principal_id": "user-123",
            "principal_kind": "user",
            "name": "my-api-key",
        },
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 201
    api_key_id = response.json()["api_key_id"]
    plaintext = response.json()["plaintext"]

    # Revoke the token
    response = await client.delete(
        f"/v1/tokens/{api_key_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 204

    # Verify the token is revoked by trying to verify it
    async with async_session_maker() as session:
        svc = ApiKeyService(session)
        from server.app.auth.api_key import ApiKeyRevoked
        with pytest.raises(ApiKeyRevoked):
            await svc.verify(plaintext)


@pytest.mark.asyncio
async def test_revoke_token_without_bearer_401(client: httpx.AsyncClient):
    """DELETE /v1/tokens/{id} without admin bearer returns 401."""
    response = await client.delete("/v1/tokens/some-id")
    assert response.status_code == 401
