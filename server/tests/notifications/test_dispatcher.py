"""Tests for NotificationDispatcher + built-in backends."""

from __future__ import annotations

from typing import Any

import pytest

from server.app.models.notification import Notification, NotificationProvider
from server.app.notifications.backends import smtp_backend, webhook_backend
from server.app.notifications.dispatcher import (
    NotificationDispatcher,
    NotificationMessage,
    NotificationResult,
)


def _notif(provider: NotificationProvider, config: dict[str, Any], enabled: bool = True) -> Notification:
    return Notification(
        id="n-1",
        name="test",
        provider=provider,
        config=config,
        enabled=enabled,
    )


@pytest.mark.asyncio
async def test_dispatcher_returns_no_backend_when_unregistered() -> None:
    d = NotificationDispatcher()
    n = _notif(NotificationProvider.WEBHOOK, {"url": "https://example.com"})
    msg = NotificationMessage(title="t", body="b")
    r = await d.send(n, msg)
    assert not r.ok
    assert "no_backend_registered" in (r.detail or "")


@pytest.mark.asyncio
async def test_dispatcher_disabled_short_circuits() -> None:
    d = NotificationDispatcher()

    async def _ok(_c: dict, _m: NotificationMessage) -> NotificationResult:
        return NotificationResult(ok=True, provider="webhook")

    d.register(NotificationProvider.WEBHOOK, _ok)
    n = _notif(NotificationProvider.WEBHOOK, {}, enabled=False)
    r = await d.send(n, NotificationMessage(title="t", body="b"))
    assert not r.ok
    assert r.detail == "disabled"


@pytest.mark.asyncio
async def test_dispatcher_retries_on_transient_failure() -> None:
    calls = {"n": 0}

    async def _flaky(_c: dict, _m: NotificationMessage) -> NotificationResult:
        calls["n"] += 1
        if calls["n"] < 3:
            return NotificationResult(ok=False, provider="webhook", detail="503")
        return NotificationResult(ok=True, provider="webhook")

    d = NotificationDispatcher(max_retries=3, backoff_seconds=0.0)
    d.register(NotificationProvider.WEBHOOK, _flaky)
    n = _notif(NotificationProvider.WEBHOOK, {})
    r = await d.send(n, NotificationMessage(title="t", body="b"))
    assert r.ok
    assert r.attempts == 3


@pytest.mark.asyncio
async def test_dispatcher_gives_up_after_max_retries() -> None:
    async def _fail(_c: dict, _m: NotificationMessage) -> NotificationResult:
        return NotificationResult(ok=False, provider="webhook", detail="boom")

    d = NotificationDispatcher(max_retries=2, backoff_seconds=0.0)
    d.register(NotificationProvider.WEBHOOK, _fail)
    n = _notif(NotificationProvider.WEBHOOK, {})
    r = await d.send(n, NotificationMessage(title="t", body="b"))
    assert not r.ok
    assert r.attempts == 3
    assert r.detail == "boom"


@pytest.mark.asyncio
async def test_dispatcher_swallows_backend_exception() -> None:
    async def _explode(_c: dict, _m: NotificationMessage) -> NotificationResult:
        raise RuntimeError("kaboom")

    d = NotificationDispatcher(max_retries=1, backoff_seconds=0.0)
    d.register(NotificationProvider.WEBHOOK, _explode)
    n = _notif(NotificationProvider.WEBHOOK, {})
    r = await d.send(n, NotificationMessage(title="t", body="b"))
    assert not r.ok
    assert "RuntimeError" in (r.detail or "")


# webhook backend


@pytest.mark.asyncio
async def test_webhook_invalid_url_short_circuits() -> None:
    r = await webhook_backend({"url": "ftp://nope"}, NotificationMessage(title="t", body="b"))
    assert not r.ok
    assert r.detail == "invalid_url"


@pytest.mark.asyncio
async def test_webhook_posts_payload(httpx_mock=None) -> None:
    """Mock HTTP server via respx-like pattern using simple httpx MockTransport."""
    import httpx

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert '"title":"alert"' in body.replace(" ", "")
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)
    # Patch httpx.AsyncClient to use mock transport for this test
    orig = httpx.AsyncClient.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = _patched_init  # type: ignore[method-assign]
    try:
        r = await webhook_backend(
            {"url": "https://example.com/hook"},
            NotificationMessage(title="alert", body="something"),
        )
        assert r.ok
        assert "status=202" in (r.detail or "")
    finally:
        httpx.AsyncClient.__init__ = orig  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_webhook_non_2xx_failure() -> None:
    import httpx

    async def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server boom")

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient.__init__

    def _patched(self, *a, **kw):
        kw["transport"] = transport
        orig(self, *a, **kw)

    httpx.AsyncClient.__init__ = _patched  # type: ignore[method-assign]
    try:
        r = await webhook_backend(
            {"url": "https://example.com"},
            NotificationMessage(title="t", body="b"),
        )
        assert not r.ok
        assert "status=500" in (r.detail or "")
    finally:
        httpx.AsyncClient.__init__ = orig  # type: ignore[method-assign]


# smtp backend (config validation only — no live SMTP)


@pytest.mark.asyncio
async def test_smtp_missing_required_config() -> None:
    r = await smtp_backend({}, NotificationMessage(title="t", body="b"))
    assert not r.ok
    assert r.detail == "missing_required_config"


@pytest.mark.asyncio
async def test_smtp_invalid_to_addrs_type() -> None:
    cfg = {"host": "localhost", "from_addr": "a@b", "to_addrs": 123}
    r = await smtp_backend(cfg, NotificationMessage(title="t", body="b"))
    assert not r.ok
    assert r.detail == "invalid_to_addrs"
