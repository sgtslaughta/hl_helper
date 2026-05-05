"""Tests for slack/discord/webhook notification backends."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from server.app.notifications import backends as backends_mod
from server.app.notifications.backends import (
    discord_backend,
    slack_backend,
    webhook_backend,
)
from server.app.notifications.dispatcher import NotificationMessage


_OriginalAsyncClient = httpx.AsyncClient


def _patch_client(monkeypatch: pytest.MonkeyPatch, status_code: int, capture: list[httpx.Request]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(request)
        return httpx.Response(status_code, text="ok")

    transport = httpx.MockTransport(handler)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return _OriginalAsyncClient(*args, **kwargs)

    monkeypatch.setattr(backends_mod.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_slack_invalid_url() -> None:
    res = await slack_backend({"webhook_url": "http://evil.example/x"}, NotificationMessage(title="t", body="b"))
    assert not res.ok
    assert res.detail == "invalid_webhook_url"


@pytest.mark.asyncio
async def test_slack_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[httpx.Request] = []
    _patch_client(monkeypatch, 200, captured)
    res = await slack_backend(
        {"webhook_url": "https://hooks.slack.com/services/X/Y/Z", "channel": "#ops"},
        NotificationMessage(title="boom", body="details", severity="error", metadata={"host": "h1"}),
    )
    assert res.ok, res.detail
    assert len(captured) == 1
    body = captured[0].read()
    assert b"#ops" in body
    assert b"boom" in body
    assert b"d62728" in body


@pytest.mark.asyncio
async def test_discord_invalid_url() -> None:
    res = await discord_backend({"webhook_url": "https://example.com/wh"}, NotificationMessage(title="t", body="b"))
    assert not res.ok


@pytest.mark.asyncio
async def test_discord_payload_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[httpx.Request] = []
    _patch_client(monkeypatch, 200, captured)
    metadata = {f"k{i}": f"v{i}" for i in range(40)}
    res = await discord_backend(
        {"webhook_url": "https://discord.com/api/webhooks/1/abc"},
        NotificationMessage(title="t", body="b" * 5000, severity="critical", metadata=metadata),
    )
    assert res.ok, res.detail
    body = captured[0].read()
    assert b"b" * 4001 not in body


@pytest.mark.asyncio
async def test_webhook_non_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[httpx.Request] = []
    _patch_client(monkeypatch, 500, captured)
    res = await webhook_backend(
        {"url": "https://example.com/wh"},
        NotificationMessage(title="t", body="b"),
    )
    assert not res.ok
    assert "status=500" in (res.detail or "")
