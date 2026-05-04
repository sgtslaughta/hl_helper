"""HashiCorp Vault backend implementing the SecretsBackend Protocol.

Wraps the synchronous ``hvac`` client via ``asyncio.to_thread`` so coroutines
do not block the event loop. Supports KV v2 read/write/version/delete plus
transit sign and lease renewal helpers used elsewhere in the broker.

Auth methods (selected by ``auth_method`` kwarg):
    - ``token``      -- ``token`` kwarg or ``VAULT_TOKEN`` env var
    - ``approle``    -- ``role_id`` + ``secret_id``
    - ``kubernetes`` -- ``role`` + ``jwt_path`` (default service-account token)
    - ``jwt``        -- ``role`` + ``jwt``

Construction is non-blocking: ``__init__`` only stores config and instantiates
the ``hvac.Client``. Authentication (login) for non-token methods runs lazily
on first use via ``connect()`` (which is in turn invoked by
``_ensure_connected()`` from each public async method). This keeps the event
loop unblocked at startup.

KV v2 paths follow the convention ``"{mount}/data/{path}"`` (e.g.
``"kv/data/foo"``); the backend splits on ``/data/`` to determine the mount
point and the secret path passed to hvac. When the path does not contain
``/data/`` the backend falls back to mount ``"secret"`` (Vault's default
KV v2 mount on dev servers) and treats the entire input as the sub-path.

Binary safety: KV v2 values are stored as strings. To round-trip arbitrary
bytes we encode using ``latin1`` (1:1 byte<->codepoint mapping) on write and
re-encode on read. Latin1 was chosen over base64 because Vault treats KV
values as strings and latin1 preserves each byte as a single character with
no padding/length expansion.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from typing import Any, Literal

import hvac
import hvac.exceptions

AuthMethod = Literal["token", "approle", "kubernetes", "jwt"]

_DEFAULT_K8S_JWT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"

# Health check cache TTL in seconds.
_HEALTH_TTL_S = 5.0


class SealedError(RuntimeError):
    """Raised when Vault reports sealed during a get/put."""


def _split_kv_path(path: str) -> tuple[str, str]:
    """Split ``"mount/data/sub/path"`` into ``(mount, "sub/path")``.

    Falls back to ``("secret", path)`` when ``/data/`` is absent. The
    ``"secret"`` default matches Vault's out-of-the-box KV v2 mount used
    by ``vault server -dev``; callers wanting a different mount must
    use the explicit ``"{mount}/data/{path}"`` form.
    """
    if "/data/" in path:
        mount, _, rest = path.partition("/data/")
        return mount, rest
    return "secret", path


class VaultBackend:
    """SecretsBackend implementation backed by HashiCorp Vault."""

    def __init__(
        self,
        *,
        url: str,
        auth_method: AuthMethod = "token",
        token: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        role: str | None = None,
        jwt: str | None = None,
        jwt_path: str = _DEFAULT_K8S_JWT_PATH,
    ) -> None:
        # Validate auth method early so misconfiguration fails fast
        # without waiting for first call.
        if auth_method not in ("token", "approle", "kubernetes", "jwt"):
            raise ValueError(f"unknown auth_method: {auth_method}")
        if auth_method == "approle" and (not role_id or not secret_id):
            raise ValueError("approle auth requires role_id and secret_id")
        if auth_method == "kubernetes" and not role:
            raise ValueError("kubernetes auth requires role")
        if auth_method == "jwt" and (not role or not jwt):
            raise ValueError("jwt auth requires role and jwt")

        self.url = url
        self.auth_method: AuthMethod = auth_method
        self._role_id = role_id
        self._secret_id = secret_id
        self._role = role
        self._jwt = jwt
        self._jwt_path = jwt_path

        client_kwargs: dict[str, Any] = {"url": url}
        if auth_method == "token":
            tok = token or os.environ.get("VAULT_TOKEN")
            if tok:
                client_kwargs["token"] = tok

        self._client = hvac.Client(**client_kwargs)
        self._connected: bool = auth_method == "token"
        self._connect_lock = asyncio.Lock()
        self._health_cache: tuple[float, dict[str, Any]] | None = None

    # ------------------------------------------------------------------ #
    # Connect / lazy login
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """Perform auth login (idempotent). Runs in a worker thread."""
        async with self._connect_lock:
            if self._connected:
                return

            def _login() -> None:
                if self.auth_method == "approle":
                    self._client.auth.approle.login(
                        role_id=self._role_id, secret_id=self._secret_id
                    )
                elif self.auth_method == "kubernetes":
                    with open(self._jwt_path, "r", encoding="utf-8") as f:
                        jwt_token = f.read().strip()
                    self._client.auth.kubernetes.login(
                        role=self._role, jwt=jwt_token
                    )
                elif self.auth_method == "jwt":
                    self._client.auth.jwt.jwt_login(
                        role=self._role, jwt=self._jwt
                    )

            await asyncio.to_thread(_login)
            self._connected = True

    async def _ensure_connected(self) -> None:
        if not self._connected:
            await self.connect()

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    async def health_check(self) -> dict[str, Any]:
        """Return ``{sealed, initialized, version}`` snapshot from sys/health.

        Result is cached for ``_HEALTH_TTL_S`` seconds to avoid hitting
        ``sys/health`` on every operation.
        """
        await self._ensure_connected()
        now = time.monotonic()
        cached = self._health_cache
        if cached is not None and (now - cached[0]) < _HEALTH_TTL_S:
            return cached[1]

        raw = await asyncio.to_thread(
            self._client.sys.read_health_status, method="GET"
        )
        data: dict[str, Any]
        if isinstance(raw, dict):
            data = raw
        else:
            # hvac may return a requests.Response under some configurations.
            try:
                data = raw.json()
            except Exception:
                data = {}
        result = {
            "sealed": bool(data.get("sealed", False)),
            "initialized": bool(data.get("initialized", False)),
            "version": str(data.get("version", "")),
        }
        self._health_cache = (now, result)
        return result

    async def _ensure_unsealed(self) -> None:
        h = await self.health_check()
        if h["sealed"]:
            raise SealedError("vault is sealed")

    # ------------------------------------------------------------------ #
    # KV v2
    # ------------------------------------------------------------------ #

    async def get(self, path: str, version: int | None = None) -> bytes:
        """Read a KV v2 secret. Returns single field as bytes else JSON dict.

        Raises:
            KeyError: when Vault returns 404 (``InvalidPath``).
            SealedError: when Vault is sealed.
        """
        await self._ensure_connected()
        await self._ensure_unsealed()
        mount, sub = _split_kv_path(path)

        def _read() -> dict[str, Any]:
            kwargs: dict[str, Any] = {"path": sub, "mount_point": mount}
            if version is not None:
                kwargs["version"] = version
            result: dict[str, Any] = self._client.secrets.kv.v2.read_secret_version(
                **kwargs
            )
            return result

        try:
            resp = await asyncio.to_thread(_read)
        except hvac.exceptions.InvalidPath as e:
            raise KeyError(path) from e
        data = resp.get("data", {}).get("data", {}) if isinstance(resp, dict) else {}
        if not isinstance(data, dict):
            raise KeyError(path)
        if len(data) == 1:
            (only,) = data.values()
            if isinstance(only, bytes):
                return only
            if isinstance(only, str):
                # Round-trip latin1 to recover original bytes.
                return only.encode("latin1")
            return str(only).encode("utf-8")
        return json.dumps(data, sort_keys=True).encode("utf-8")

    async def put(self, path: str, value: bytes) -> int:
        """Write a KV v2 secret as ``{"value": <latin1-decoded>}``; return version.

        Bytes are decoded via ``latin1`` (lossless 1:1 byte mapping) so
        arbitrary binary payloads round-trip safely through Vault's
        string-typed KV values.
        """
        await self._ensure_connected()
        await self._ensure_unsealed()
        mount, sub = _split_kv_path(path)
        secret = {"value": value.decode("latin1")}

        def _write() -> dict[str, Any]:
            result: dict[str, Any] = self._client.secrets.kv.v2.create_or_update_secret(
                path=sub, secret=secret, mount_point=mount
            )
            return result

        resp = await asyncio.to_thread(_write)
        if isinstance(resp, dict):
            ver = resp.get("data", {}).get("version")
            if isinstance(ver, int):
                return ver
        raise RuntimeError(f"unexpected vault put response shape: {resp!r}")

    async def versions(self, path: str) -> list[int]:
        """List KV v2 versions via metadata.

        Raises:
            KeyError: when Vault returns 404 (``InvalidPath``).
        """
        await self._ensure_connected()
        await self._ensure_unsealed()
        mount, sub = _split_kv_path(path)

        def _meta() -> dict[str, Any]:
            result: dict[str, Any] = self._client.secrets.kv.v2.read_secret_metadata(
                path=sub, mount_point=mount
            )
            return result

        try:
            resp = await asyncio.to_thread(_meta)
        except hvac.exceptions.InvalidPath as e:
            raise KeyError(path) from e
        if not isinstance(resp, dict):
            return []
        versions_obj = resp.get("data", {}).get("versions", {})
        if not isinstance(versions_obj, dict):
            return []
        return sorted(int(k) for k in versions_obj.keys())

    async def delete(self, path: str, version: int | None = None) -> None:
        """Destroy a specific version, or all metadata when version is None.

        Raises:
            KeyError: when Vault returns 404 (``InvalidPath``).
        """
        await self._ensure_connected()
        await self._ensure_unsealed()
        mount, sub = _split_kv_path(path)
        try:
            if version is None:
                await asyncio.to_thread(
                    self._client.secrets.kv.v2.delete_metadata_and_all_versions,
                    path=sub,
                    mount_point=mount,
                )
                return
            await asyncio.to_thread(
                self._client.secrets.kv.v2.destroy_secret_versions,
                path=sub,
                versions=[version],
                mount_point=mount,
            )
        except hvac.exceptions.InvalidPath as e:
            raise KeyError(path) from e

    # ------------------------------------------------------------------ #
    # Transit + leases
    # ------------------------------------------------------------------ #

    async def transit_sign(self, key_name: str, data: bytes) -> str:
        """Sign ``data`` via Vault transit using sha2-256."""
        await self._ensure_connected()
        encoded = base64.b64encode(data).decode("ascii")

        def _sign() -> dict[str, Any]:
            result: dict[str, Any] = self._client.secrets.transit.sign_data(
                name=key_name,
                hash_input=encoded,
                hash_algorithm="sha2-256",
            )
            return result

        resp = await asyncio.to_thread(_sign)
        if isinstance(resp, dict):
            sig = resp.get("data", {}).get("signature")
            if isinstance(sig, str):
                return sig
        raise RuntimeError("transit sign did not return a signature")

    async def renew_lease(self, lease_id: str) -> None:
        """Renew a Vault lease."""
        await self._ensure_connected()
        await asyncio.to_thread(self._client.sys.renew_lease, lease_id=lease_id)
