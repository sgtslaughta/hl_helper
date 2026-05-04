"""HTTP-based secrets backend for out-of-process plugin runtimes.

Wraps an arbitrary plugin endpoint (HTTP URL or HTTP-over-Unix-socket) and
speaks a tiny JSON protocol so plugin authors don't need to depend on FastAPI
specifics. Each method serializes a single ``POST <endpoint>`` request:

    {"action": "get"|"put"|"versions"|"delete", "path": str,
     "value_b64": str | None, "version": int | None}

The plugin replies with:

    {"ok": bool, "value_b64": str?, "version": int?, "versions": list[int]?,
     "error": str?}

On HTTP-level failure (non-2xx, transport error) or ``ok=false``, the backend
raises :class:`BackendError`. The C6 plugin runtime hosts the actual server.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from server.app.secrets.backends.base import BackendError


class PluginBackend:
    """SecretsBackend implementation that proxies to an HTTP plugin endpoint.

    Args:
        endpoint: Base URL the plugin listens on (HTTP or HTTP-over-UDS form).
        proxies: Optional egress proxy URL (e.g. ``http://proxy:3128``); when
            set it is forwarded to the underlying ``httpx.AsyncClient``.
        timeout_s: Per-request timeout in seconds.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        proxies: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._proxies = proxies
        self._timeout_s = timeout_s

        client_kwargs: dict[str, Any] = {"timeout": timeout_s}
        if proxies is not None:
            # httpx >=0.28 prefers ``proxy`` (singular); older releases use
            # ``proxies``. Pass whichever the installed version accepts.
            try:
                client_kwargs["proxy"] = proxies
                self._client = httpx.AsyncClient(**client_kwargs)
            except TypeError:  # pragma: no cover - legacy httpx
                client_kwargs.pop("proxy", None)
                client_kwargs["proxies"] = proxies
                self._client = httpx.AsyncClient(**client_kwargs)
        else:
            self._client = httpx.AsyncClient(**client_kwargs)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _call(self, action: str, **payload: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"action": action}
        body.update(payload)
        try:
            resp = await self._client.post(self.endpoint, json=body)
        except httpx.HTTPError as e:
            raise BackendError(f"plugin transport error: {e}") from e
        if resp.status_code >= 400:
            raise BackendError(
                f"plugin http {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise BackendError(f"plugin response not json: {e}") from e
        if not isinstance(data, dict):
            raise BackendError("plugin response not an object")
        if not data.get("ok", False):
            raise BackendError(str(data.get("error") or "plugin returned ok=false"))
        return data

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # SecretsBackend protocol
    # ------------------------------------------------------------------ #

    async def get(self, path: str, version: int | None = None) -> bytes:
        data = await self._call("get", path=path, version=version)
        b64 = data.get("value_b64")
        if not isinstance(b64, str):
            raise BackendError("plugin get: missing value_b64")
        try:
            return base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise BackendError(f"plugin get: invalid base64: {e}") from e

    async def put(self, path: str, value: bytes) -> int:
        b64 = base64.b64encode(value).decode("ascii")
        data = await self._call("put", path=path, value_b64=b64)
        ver = data.get("version")
        if not isinstance(ver, int) or isinstance(ver, bool):
            raise BackendError("plugin put: missing version")
        return ver

    async def versions(self, path: str) -> list[int]:
        data = await self._call("versions", path=path)
        raw = data.get("versions", [])
        if not isinstance(raw, list):
            raise BackendError("plugin versions: not a list")
        return [int(v) for v in raw]

    async def delete(self, path: str, version: int | None = None) -> None:
        await self._call("delete", path=path, version=version)
