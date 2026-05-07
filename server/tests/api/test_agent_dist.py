"""Tests for /agent/ endpoint suite."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient

from server.app.api.app import create_app
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
def ca_fixture(tmp_path: Path):
    """Return bootstrapped CA for tests."""
    from server.app.crypto.ca import InternalCA
    return InternalCA.bootstrap(tmp_path / "ca")


@pytest.mark.asyncio
async def test_get_agent_binary_amd64_deprecated(sm, ca_fixture, tmp_path):
    """GET /agent/{arch}/hl-agent returns binary (deprecated route)."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a test binary
    dist_dir = tmp_path / "agent-dist"
    dist_dir.mkdir()
    binary_path = dist_dir / "hl-agent-amd64"
    binary_path.write_bytes(b"ELF_BINARY_DATA")

    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get("/agent/amd64/hl-agent", follow_redirects=False)

    assert r.status_code == 200
    assert r.content == b"ELF_BINARY_DATA"
    assert r.headers["content-disposition"] == 'attachment; filename="hl-agent"'


@pytest.mark.asyncio
async def test_get_agent_binary_fallback(sm, ca_fixture, tmp_path):
    """GET /agent/{arch}/hl-agent falls back to single binary (deprecated route)."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a test binary (single, no arch suffix)
    dist_dir = tmp_path / "agent-dist"
    dist_dir.mkdir()
    binary_path = dist_dir / "hl-agent"
    binary_path.write_bytes(b"ELF_FALLBACK_DATA")

    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get("/agent/arm64/hl-agent", follow_redirects=False)

    assert r.status_code == 200
    assert r.content == b"ELF_FALLBACK_DATA"


@pytest.mark.asyncio
async def test_get_agent_binary_unsupported_arch(sm, ca_fixture, tmp_path):
    """GET /agent/{unsupported_arch}/hl-agent returns 400."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    dist_dir = tmp_path / "agent-dist"
    dist_dir.mkdir()

    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get("/agent/unsupported/hl-agent", follow_redirects=False)

    assert r.status_code == 400
    assert "unsupported arch" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_agent_binary_not_found(sm, ca_fixture, tmp_path):
    """GET /agent/{arch}/hl-agent returns 404 when binary missing."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    dist_dir = tmp_path / "agent-dist"
    dist_dir.mkdir()

    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get("/agent/amd64/hl-agent", follow_redirects=False)

    assert r.status_code == 404
    assert "agent binary not found" in r.json()["detail"]


@pytest.mark.asyncio
async def test_agent_latest_redirect(sm, ca_fixture, tmp_path):
    """GET /agent/{arch}/latest redirects to /v1/agent-releases/latest."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    with mock.patch.dict("os.environ", {}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get("/agent/amd64/latest", follow_redirects=False)

    assert r.status_code == 307
    assert r.headers["location"] == "/v1/agent-releases/latest?os=linux&arch=amd64"


@pytest.mark.asyncio
async def test_agent_latest_unsupported_arch(sm, ca_fixture, tmp_path):
    """GET /agent/{unsupported_arch}/latest returns 400."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    with mock.patch.dict("os.environ", {}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get("/agent/invalid/latest", follow_redirects=False)

    assert r.status_code == 400
    assert "unsupported arch" in r.json()["detail"]
