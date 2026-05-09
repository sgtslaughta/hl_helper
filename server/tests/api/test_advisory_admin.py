"""Tests for /v1/advisories/feeds admin endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from unittest import mock

from server.app.api.app import create_app
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-tok"}


@pytest.fixture
def mock_settings() -> FleetSettings:
    return FleetSettings(admin_token=SecretStr("test-tok"))


class _StubWorker:
    """In-memory stand-in for AdvisoryWorker."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str]] = []
        self.return_status = [
            {
                "feed": "osv",
                "last_sync_at": "2026-05-08T12:00:00+00:00",
                "last_count": 42,
                "last_error": None,
                "next_scheduled_at": "2026-05-08T18:00:00+00:00",
                "in_progress": False,
            },
            {
                "feed": "epss",
                "last_sync_at": None,
                "last_count": 0,
                "last_error": None,
                "next_scheduled_at": None,
                "in_progress": True,
            },
            {
                "feed": "kev",
                "last_sync_at": None,
                "last_count": 0,
                "last_error": "boom",
                "next_scheduled_at": None,
                "in_progress": False,
            },
        ]
        self.queue_full = False

    def enqueue_feed_sync(self, feed_name: str, *, trigger: str = "manual") -> bool:
        if self.queue_full:
            return False
        self.enqueued.append((feed_name, trigger))
        return True

    async def get_status(self) -> list[dict]:
        return self.return_status


@pytest.mark.asyncio
async def test_status_returns_three_feeds(auth, sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    state.advisory_worker = _StubWorker()
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.get("/v1/advisories/feeds/status", headers=auth)

    assert resp.status_code == 200
    body = resp.json()
    feeds = body["feeds"]
    names = [f["feed"] for f in feeds]
    assert names == ["osv", "epss", "kev"]
    assert feeds[0]["last_count"] == 42
    assert feeds[1]["in_progress"] is True
    assert feeds[2]["last_error"] == "boom"


@pytest.mark.asyncio
async def test_status_when_worker_disabled_returns_empty_rollup(auth, sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    state.advisory_worker = None
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.get("/v1/advisories/feeds/status", headers=auth)

    assert resp.status_code == 200
    feeds = resp.json()["feeds"]
    assert [f["feed"] for f in feeds] == ["osv", "epss", "kev"]
    assert all(f["last_sync_at"] is None for f in feeds)


@pytest.mark.asyncio
async def test_sync_all_enqueues_three(auth, sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    worker = _StubWorker()
    state.advisory_worker = worker
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/v1/advisories/feeds/sync?feed=all", headers=auth
            )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert sorted(body["feeds"]) == ["epss", "kev", "osv"]
    assert sorted(c[0] for c in worker.enqueued) == ["epss", "kev", "osv"]


@pytest.mark.asyncio
async def test_sync_specific_feed(auth, sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    worker = _StubWorker()
    state.advisory_worker = worker
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/v1/advisories/feeds/sync?feed=osv", headers=auth
            )

    assert resp.status_code == 202
    assert resp.json()["feeds"] == ["osv"]
    assert worker.enqueued == [("osv", "manual")]


@pytest.mark.asyncio
async def test_sync_when_worker_unavailable_returns_503(auth, sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    state.advisory_worker = None
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/v1/advisories/feeds/sync?feed=all", headers=auth
            )

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_sync_requires_admin(sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    state.advisory_worker = _StubWorker()
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.post("/v1/advisories/feeds/sync?feed=all")

    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_sync_full_queue_returns_queue_full(auth, sm, mock_settings):
    app = create_app()
    state = make_test_app_state(sessionmaker=sm)
    worker = _StubWorker()
    worker.queue_full = True
    state.advisory_worker = worker
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/v1/advisories/feeds/sync?feed=all", headers=auth
            )

    assert resp.status_code == 202
    assert resp.json()["status"] == "queue_full"
