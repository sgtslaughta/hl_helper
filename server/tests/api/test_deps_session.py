"""Tests for session token extraction in deps.current_principal."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI, Depends

from server.app.auth.sessions import SessionService, make_request_meta
from server.app.db.session import make_engine, make_sessionmaker
from server.app.deps import current_principal
from server.app.events.bus import Bus
from server.app.models import Base, User
from server.app.models.user import UserKind
from server.app.rbac.provider import Principal
from server.tests._helpers.app_state import make_test_app_state


@pytest.mark.asyncio
async def test_session_bearer_token_extraction():
    """Test extraction of session from Authorization: Bearer header."""
    # Setup database
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    # Create test user
    async with sm() as session:
        user = User(id="user-123", email="test@example.com", kind=UserKind.LOCAL)
        session.add(user)
        await session.commit()

    # Create session service and issue token
    bus = Bus()
    session_service = SessionService(sessionmaker=sm, bus=bus)
    await session_service.start()

    async with sm() as session:
        user = (await session.get(User, "user-123"))

    request_meta = make_request_meta("127.0.0.1", "")
    issue = await session_service.issue(user, "none", request_meta)
    token = issue.raw

    # Create FastAPI app with principal dependency
    app = FastAPI()

    @app.get("/test")
    async def test_route(principal: Principal | None = Depends(current_principal)):
        if principal:
            return {"user_id": principal.user_id}
        return {"user_id": None}

    # Wire app_state
    app_state = make_test_app_state(
        sessionmaker=sm,
        session_service=session_service,
    )
    app.state.app_state = app_state

    # Test with bearer token
    client = TestClient(app)
    response = client.get("/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-123"

    await session_service.stop()
    await engine.dispose()


@pytest.mark.asyncio
async def test_session_cookie_extraction():
    """Test extraction of session from hls_session cookie."""
    # Setup database
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    # Create test user
    async with sm() as session:
        user = User(id="user-456", email="test@example.com", kind=UserKind.LOCAL)
        session.add(user)
        await session.commit()

    # Create session service and issue token
    bus = Bus()
    session_service = SessionService(sessionmaker=sm, bus=bus)
    await session_service.start()

    async with sm() as session:
        user = (await session.get(User, "user-456"))

    request_meta = make_request_meta("127.0.0.1", "")
    issue = await session_service.issue(user, "none", request_meta)
    token = issue.raw

    # Create FastAPI app
    app = FastAPI()

    @app.get("/test")
    async def test_route(principal: Principal | None = Depends(current_principal)):
        if principal:
            return {"user_id": principal.user_id}
        return {"user_id": None}

    # Wire app_state
    app_state = make_test_app_state(
        sessionmaker=sm,
        session_service=session_service,
    )
    app.state.app_state = app_state

    # Test with cookie
    client = TestClient(app)
    response = client.get("/test", cookies={"hls_session": token})
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-456"

    await session_service.stop()
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_session_returns_none():
    """Test that missing session token returns None principal."""
    # Setup database
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    # Create session service
    bus = Bus()
    session_service = SessionService(sessionmaker=sm, bus=bus)
    await session_service.start()

    # Create FastAPI app
    app = FastAPI()

    @app.get("/test")
    async def test_route(principal: Principal | None = Depends(current_principal)):
        if principal:
            return {"user_id": principal.user_id}
        return {"user_id": None}

    # Wire app_state
    app_state = make_test_app_state(
        sessionmaker=sm,
        session_service=session_service,
    )
    app.state.app_state = app_state

    # Test without session
    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json()["user_id"] is None

    await session_service.stop()
    await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_session_token_returns_none():
    """Test that invalid session token returns None principal."""
    # Setup database
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = make_sessionmaker(engine)

    # Create session service
    bus = Bus()
    session_service = SessionService(sessionmaker=sm, bus=bus)
    await session_service.start()

    # Create FastAPI app
    app = FastAPI()

    @app.get("/test")
    async def test_route(principal: Principal | None = Depends(current_principal)):
        if principal:
            return {"user_id": principal.user_id}
        return {"user_id": None}

    # Wire app_state
    app_state = make_test_app_state(
        sessionmaker=sm,
        session_service=session_service,
    )
    app.state.app_state = app_state

    # Test with invalid bearer token
    client = TestClient(app)
    response = client.get("/test", headers={"Authorization": "Bearer hls_invalid"})
    assert response.status_code == 200
    assert response.json()["user_id"] is None

    await session_service.stop()
    await engine.dispose()
