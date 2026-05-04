"""Tests for PluginBackend (HTTP-over-plugin secrets backend)."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from server.app.secrets.backends.base import BackendError
from server.app.secrets.backends.plugin import PluginBackend
from server.app.secrets.broker import SecretsBroker
from server.app.secrets.cache import BrokerCache
from server.app.secrets.handle import HandleStore
from server.app.secrets.ref import SecretRef


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ok(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, **payload})


def _err(error: str = "boom") -> httpx.Response:
    return httpx.Response(200, json={"ok": False, "error": error})


def _make_backend(handler, *, proxies: str | None = None) -> PluginBackend:
    """Build a PluginBackend whose AsyncClient uses MockTransport(handler)."""
    transport = httpx.MockTransport(handler)
    backend = PluginBackend(endpoint="http://plugin.local", proxies=proxies)
    # Replace the AsyncClient with one wired to the mock transport.
    backend._client = httpx.AsyncClient(transport=transport)
    return backend


# --------------------------------------------------------------------------- #
# get
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_returns_decoded_bytes() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.read()
        b64 = base64.b64encode(b"hello world").decode("ascii")
        return _ok({"value_b64": b64, "version": 3})

    backend = _make_backend(handler)
    val = await backend.get("foo")
    assert val == b"hello world"


@pytest.mark.asyncio
async def test_get_raises_keyerror_on_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "not_found"})

    backend = _make_backend(handler)
    with pytest.raises(BackendError):
        await backend.get("missing")


# --------------------------------------------------------------------------- #
# put
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_put_returns_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"version": 7})

    backend = _make_backend(handler)
    v = await backend.put("foo", b"data")
    assert v == 7


# --------------------------------------------------------------------------- #
# error paths
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stub_returns_ok_false_raises_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _err("forbidden")

    backend = _make_backend(handler)
    with pytest.raises(BackendError) as exc:
        await backend.put("foo", b"x")
    assert "forbidden" in str(exc.value)


@pytest.mark.asyncio
async def test_network_error_raises_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    backend = _make_backend(handler)
    with pytest.raises(BackendError):
        await backend.get("foo")


@pytest.mark.asyncio
async def test_http_error_status_raises_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "kaboom"})

    backend = _make_backend(handler)
    with pytest.raises(BackendError):
        await backend.get("foo")


@pytest.mark.asyncio
async def test_non_json_response_raises_backend_error() -> None:
    """Plugin returning non-JSON body should raise BackendError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="this is not json")

    backend = _make_backend(handler)
    with pytest.raises(BackendError, match="not json"):
        await backend.get("foo")


@pytest.mark.asyncio
async def test_response_array_raises_backend_error() -> None:
    """Plugin returning JSON array instead of object should raise BackendError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    backend = _make_backend(handler)
    with pytest.raises(BackendError, match="not an object"):
        await backend.get("foo")


@pytest.mark.asyncio
async def test_get_missing_value_b64_raises_backend_error() -> None:
    """Plugin get response without value_b64 should raise BackendError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    backend = _make_backend(handler)
    with pytest.raises(BackendError, match="missing value_b64"):
        await backend.get("foo")


@pytest.mark.asyncio
async def test_get_invalid_base64_raises_backend_error() -> None:
    """Plugin get response with invalid base64 should raise BackendError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "value_b64": "!!!not-valid-b64!!!"})

    backend = _make_backend(handler)
    with pytest.raises(BackendError, match="invalid base64"):
        await backend.get("foo")


@pytest.mark.asyncio
async def test_put_bool_version_raises_backend_error() -> None:
    """Plugin returning version=true (bool) should raise BackendError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "version": True})

    backend = _make_backend(handler)
    with pytest.raises(BackendError, match="missing version"):
        await backend.put("foo", b"data")


@pytest.mark.asyncio
async def test_versions_non_list_raises_backend_error() -> None:
    """Plugin returning versions as non-list should raise BackendError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "versions": "oops"})

    backend = _make_backend(handler)
    with pytest.raises(BackendError, match="not a list"):
        await backend.versions("foo")


# --------------------------------------------------------------------------- #
# versions / delete
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_versions_returns_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"versions": [1, 2, 3]})

    backend = _make_backend(handler)
    out = await backend.versions("foo")
    assert out == [1, 2, 3]


@pytest.mark.asyncio
async def test_delete_does_not_raise_on_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({})

    backend = _make_backend(handler)
    await backend.delete("foo")


# --------------------------------------------------------------------------- #
# egress proxy
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_egress_proxy_passed_to_async_client() -> None:
    """When proxies is set, AsyncClient is constructed with proxies kwarg."""
    with patch("server.app.secrets.backends.plugin.httpx.AsyncClient") as cls:
        instance = MagicMock()
        instance.aclose = AsyncMock()
        cls.return_value = instance
        PluginBackend(endpoint="http://plugin.local", proxies="http://proxy:3128")
        # Verify proxies kwarg was passed.
        kwargs = cls.call_args.kwargs
        assert kwargs.get("proxies") == "http://proxy:3128" or \
               kwargs.get("proxy") == "http://proxy:3128"


@pytest.mark.asyncio
async def test_no_proxy_when_none() -> None:
    """When proxies is None, no proxies kwarg is passed."""
    with patch("server.app.secrets.backends.plugin.httpx.AsyncClient") as cls:
        instance = MagicMock()
        instance.aclose = AsyncMock()
        cls.return_value = instance
        PluginBackend(endpoint="http://plugin.local")
        kwargs = cls.call_args.kwargs
        assert "proxies" not in kwargs and "proxy" not in kwargs


# --------------------------------------------------------------------------- #
# Broker integration
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_secret_ref_routes_through_plugin_backend() -> None:
    """SecretRef("secret://stub/foo") routes through PluginBackend registered as 'stub'."""
    def handler(request: httpx.Request) -> httpx.Response:
        b64 = base64.b64encode(b"plugin-value").decode("ascii")
        return _ok({"value_b64": b64, "version": 1})

    backend = _make_backend(handler)
    broker = SecretsBroker(
        backends={"stub": backend},
        cache=BrokerCache(ttl_seconds=30),
        handle_store=HandleStore(),
    )

    ref = SecretRef.parse("secret://stub/foo")
    requester = MagicMock(user_id="u1")
    h = await broker.get(ref, requester=requester)
    # Reveal via internal raw fetch (bypass MFA since not configured).
    val = await broker._raw_get(ref)
    assert val == b"plugin-value"
    assert h is not None


# --------------------------------------------------------------------------- #
# T7: list_refs for unknown backend raises KeyError
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_refs_unknown_backend_raises_keyerror() -> None:
    """Broker.list_refs with a backend not in the registry raises KeyError."""
    backend = _make_backend(lambda r: _ok({}))
    broker = SecretsBroker(
        backends={"stub": backend},
        cache=BrokerCache(ttl_seconds=30),
        handle_store=HandleStore(),
    )
    with pytest.raises(KeyError):
        await broker.list_refs("missing")


# --------------------------------------------------------------------------- #
# T9: SecretRef with #field through broker._raw_get
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_field_separator_in_ref_path() -> None:
    """SecretRef with #field passes path#field to backend.get()."""
    import json as _json

    captured_path: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        captured_path["path"] = body.get("path")
        b64 = base64.b64encode(b"field-value").decode("ascii")
        return _ok({"value_b64": b64, "version": 1})

    backend = _make_backend(handler)
    broker = SecretsBroker(
        backends={"stub": backend},
        cache=BrokerCache(ttl_seconds=30),
        handle_store=HandleStore(),
    )
    ref = SecretRef.parse("secret://stub/kv/data/creds#password")
    val = await broker._raw_get(ref)
    assert val == b"field-value"
    assert captured_path["path"] == "kv/data/creds#password"
