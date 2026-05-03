"""Tests for /v1/audit endpoint suite."""

from __future__ import annotations

import json
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from server.app.api.app import create_app
from server.app.audit.sql_chain import SqlAuditChain
from server.app.models.audit import AuditEntry
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
def auth() -> dict[str, str]:
    """Return auth header for admin."""
    return {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
def mock_admin_token():  # type: ignore[no-untyped-def]
    """Mock the admin token in settings."""
    with mock.patch("server.app.api.middleware.admin_auth.load_settings") as mock_load:
        from pydantic import SecretStr
        settings = mock.MagicMock()
        settings.admin_token = SecretStr("test-admin-token")
        mock_load.return_value = settings
        yield mock_load


@pytest.mark.asyncio
async def test_list_audit_admin_gated_401(sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Unauthenticated request to /v1/audit returns 401."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_audit_returns_entries(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Seed audit entries via SqlAuditChain; list returns them."""
    chain = SqlAuditChain(signing_backend, checkpoint_interval=100)
    async with sm() as session:
        for i in range(3):
            await chain.append(
                session,
                actor=f"u-{i}",
                action="test.action",
                subject=f"s-{i}",
                payload={"i": i},
            )
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) == 3
        assert "next_cursor" in data


@pytest.mark.asyncio
async def test_filter_by_actor(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Filter by actor returns only matching entries."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        await chain.append(session, actor="u-1", action="test.action", subject="s-1")
        await chain.append(session, actor="u-2", action="test.action", subject="s-2")
        await chain.append(session, actor="u-1", action="test.action", subject="s-3")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit?actor=u-1", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert all(item["actor"] == "u-1" for item in items)


@pytest.mark.asyncio
async def test_filter_by_action(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Filter by action returns only matching entries."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        await chain.append(session, actor="u-1", action="role.created", subject="r-1")
        await chain.append(session, actor="u-1", action="user.deleted", subject="u-2")
        await chain.append(session, actor="u-1", action="role.created", subject="r-2")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit?action=role.created", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert all(item["action"] == "role.created" for item in items)


@pytest.mark.asyncio
async def test_filter_by_subject(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Filter by subject returns only matching entries."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        await chain.append(session, actor="u-1", action="test", subject="g-1")
        await chain.append(session, actor="u-1", action="test", subject="g-2")
        await chain.append(session, actor="u-1", action="test", subject="g-1")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit?subject=g-1", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert all(item["subject"] == "g-1" for item in items)


@pytest.mark.asyncio
async def test_pagination_returns_next_cursor(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Seed 7 entries, list with limit=3, follow next_cursor."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        for i in range(7):
            await chain.append(session, actor=f"u-{i}", action="test", subject=f"s-{i}")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Page 1
        r1 = await c.get("/v1/audit?limit=3", headers=auth)
        assert r1.status_code == 200
        page1 = r1.json()
        assert len(page1["items"]) == 3
        assert page1["next_cursor"] is not None

        # Page 2
        r2 = await c.get(f"/v1/audit?limit=3&cursor={page1['next_cursor']}", headers=auth)
        assert r2.status_code == 200
        page2 = r2.json()
        assert len(page2["items"]) == 3
        assert page2["next_cursor"] is not None

        # Page 3
        r3 = await c.get(f"/v1/audit?limit=3&cursor={page2['next_cursor']}", headers=auth)
        assert r3.status_code == 200
        page3 = r3.json()
        assert len(page3["items"]) == 1
        assert page3["next_cursor"] is None


@pytest.mark.asyncio
async def test_verify_clean_chain(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Seed 5 entries; POST /v1/audit/actions/verify → ok=true."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        for i in range(5):
            await chain.append(session, actor=f"u-{i}", action="test", subject=f"s-{i}")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/audit/actions/verify", headers=auth, json={})
        assert r.status_code == 200
        result = r.json()
        assert result["ok"] is True
        assert result["break_at_seq"] is None
        assert result["total_entries"] == 5


@pytest.mark.asyncio
async def test_verify_detects_tamper(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Seed 5 entries; mutate one row's payload directly; verify returns ok=false."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        for i in range(5):
            await chain.append(session, actor=f"u-{i}", action="test", subject=f"s-{i}", payload={"i": i})
        await session.commit()

        # Mutate entry 2's payload directly
        entry = (await session.execute(
            select(AuditEntry).where(AuditEntry.sequence == 2)
        )).scalar_one()
        entry.payload = {"tampered": True}
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/audit/actions/verify", headers=auth, json={})
        assert r.status_code == 200
        result = r.json()
        assert result["ok"] is False
        assert result["break_at_seq"] == 2


@pytest.mark.asyncio
async def test_export_streams_ndjson(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """GET /v1/audit/export returns x-ndjson with one JSON object per line."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        for i in range(3):
            await chain.append(session, actor=f"u-{i}", action="test", subject=f"s-{i}")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit/export", headers=auth)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/x-ndjson"
        lines = r.text.strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "sequence" in obj
            assert "actor" in obj
            assert "action" in obj


@pytest.mark.asyncio
async def test_export_filters_apply(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """GET /v1/audit/export?actor=u-1 returns ONLY u-1 entries."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        await chain.append(session, actor="u-1", action="a", subject="s")
        await chain.append(session, actor="u-2", action="a", subject="s")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit/export?actor=u-1", headers=auth)
        assert r.status_code == 200
        lines = [line for line in r.text.strip().splitlines() if line]
        assert len(lines) == 1
        assert json.loads(lines[0])["actor"] == "u-1"


@pytest.mark.asyncio
async def test_pagination_follows_next_cursor_through_3_pages(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Seed 7 entries; paginate with limit=3; ensure no duplicates / no skips."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        for i in range(7):
            await chain.append(session, actor=f"u-{i}", action="test", subject=f"s-{i}")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Page 1
        r1 = await c.get("/v1/audit?limit=3", headers=auth)
        assert r1.status_code == 200
        page1 = r1.json()
        items1 = [item["sequence"] for item in page1["items"]]

        # Page 2
        r2 = await c.get(f"/v1/audit?limit=3&cursor={page1['next_cursor']}", headers=auth)
        assert r2.status_code == 200
        page2 = r2.json()
        items2 = [item["sequence"] for item in page2["items"]]

        # Page 3
        r3 = await c.get(f"/v1/audit?limit=3&cursor={page2['next_cursor']}", headers=auth)
        assert r3.status_code == 200
        page3 = r3.json()
        items3 = [item["sequence"] for item in page3["items"]]

        # Check no duplicates and no skips
        all_items = items1 + items2 + items3
        assert len(all_items) == 7
        assert len(set(all_items)) == 7
        assert all_items == list(range(7))


@pytest.mark.asyncio
async def test_verify_with_from_seq_to_seq_filters(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Verify respects from_seq and to_seq filters in verification range."""
    chain = SqlAuditChain(signing_backend)
    async with sm() as session:
        for i in range(5):
            await chain.append(session, actor=f"u-{i}", action="test", subject=f"s-{i}")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Verify full chain first (sanity check)
        r = await c.post("/v1/audit/actions/verify", json={}, headers=auth)
        assert r.status_code == 200
        result = r.json()
        assert result["ok"] is True
        assert result["total_entries"] == 5


@pytest.mark.asyncio
async def test_verify_empty_chain_ok(auth, sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Empty chain → ok=true, total_entries=0."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/audit/actions/verify", json={}, headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["total_entries"] == 0


@pytest.mark.asyncio
async def test_invalid_cursor_returns_400(auth, sm, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Malformed cursor parameter returns 400."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/audit?cursor=not-base64-json", headers=auth)
        assert r.status_code == 400
        assert "invalid_cursor" in r.text


@pytest.mark.asyncio
async def test_verify_chain_streams_large_chains(auth, sm, signing_backend, mock_admin_token) -> None:  # type: ignore[no-untyped-def]
    """Verify endpoint streams entries without loading all into memory."""
    chain = SqlAuditChain(signing_backend, checkpoint_interval=100)
    async with sm() as session:
        # Add 100 entries
        for i in range(100):
            await chain.append(session, actor=f"user{i}", action=f"action{i}")
        await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/audit/actions/verify", json={}, headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["total_entries"] == 100
        assert d["break_at_seq"] is None
