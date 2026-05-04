"""Tests for VaultBackend.

Strategy:
- Mock-based unit tests (always run): patch ``hvac.Client`` at module
  boundary ``server.app.secrets.backends.vault.hvac.Client`` and verify
  correct method calls.
- Integration tests (skipped if ``vault`` binary missing): spawn
  ``vault server -dev`` subprocess and exercise the real backend.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any, AsyncIterator, Iterator
from unittest.mock import MagicMock, patch

import hvac.exceptions
import pytest

from server.app.secrets.backends.vault import SealedError, VaultBackend, _split_kv_path


# --------------------------------------------------------------------------- #
# Mocked unit tests
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_client() -> Iterator[MagicMock]:
    """Patch ``hvac.Client`` and yield the mock instance."""
    with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
        instance = MagicMock()
        instance.is_authenticated.return_value = True
        instance.sys.read_health_status.return_value = {
            "sealed": False,
            "initialized": True,
            "version": "1.x",
        }
        cls.return_value = instance
        yield instance


@pytest.fixture
async def backend(mock_client: MagicMock) -> AsyncIterator[VaultBackend]:
    b = VaultBackend(url="http://127.0.0.1:8200", auth_method="token", token="root")
    yield b


class TestAuthMethods:
    def test_token_auth_uses_token(self) -> None:
        with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
            inst = MagicMock()
            inst.is_authenticated.return_value = True
            cls.return_value = inst
            VaultBackend(url="http://x", auth_method="token", token="root")
            kwargs = cls.call_args.kwargs
            assert kwargs.get("token") == "root"

    def test_token_auth_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VAULT_TOKEN", "env-tok")
        with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
            inst = MagicMock()
            inst.is_authenticated.return_value = True
            cls.return_value = inst
            VaultBackend(url="http://x", auth_method="token")
            kwargs = cls.call_args.kwargs
            assert kwargs.get("token") == "env-tok"

    def test_init_does_not_login_synchronously(self) -> None:
        """__init__ must NOT call login (would block the event loop)."""
        with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
            inst = MagicMock()
            inst.is_authenticated.return_value = True
            cls.return_value = inst
            VaultBackend(
                url="http://x",
                auth_method="approle",
                role_id="rid",
                secret_id="sid",
            )
            inst.auth.approle.login.assert_not_called()

    async def test_approle_calls_login_lazily(self) -> None:
        with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
            inst = MagicMock()
            inst.is_authenticated.return_value = True
            cls.return_value = inst
            b = VaultBackend(
                url="http://x",
                auth_method="approle",
                role_id="rid",
                secret_id="sid",
            )
            await b.connect()
            inst.auth.approle.login.assert_called_once_with(
                role_id="rid", secret_id="sid"
            )
            # connect() is idempotent
            await b.connect()
            inst.auth.approle.login.assert_called_once()

    async def test_kubernetes_calls_login_lazily(self, tmp_path: Any) -> None:
        jwt_file = tmp_path / "token"
        jwt_file.write_text("k8s-jwt")
        with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
            inst = MagicMock()
            inst.is_authenticated.return_value = True
            cls.return_value = inst
            b = VaultBackend(
                url="http://x",
                auth_method="kubernetes",
                role="my-role",
                jwt_path=str(jwt_file),
            )
            await b.connect()
            inst.auth.kubernetes.login.assert_called_once_with(
                role="my-role", jwt="k8s-jwt"
            )

    async def test_jwt_calls_login_lazily(self) -> None:
        with patch("server.app.secrets.backends.vault.hvac.Client") as cls:
            inst = MagicMock()
            inst.is_authenticated.return_value = True
            cls.return_value = inst
            b = VaultBackend(
                url="http://x",
                auth_method="jwt",
                role="my-role",
                jwt="jwt-token",
            )
            await b.connect()
            inst.auth.jwt.jwt_login.assert_called_once_with(
                role="my-role", jwt="jwt-token"
            )

    def test_unknown_auth_method_raises(self) -> None:
        with patch("server.app.secrets.backends.vault.hvac.Client"):
            with pytest.raises(ValueError):
                VaultBackend(url="http://x", auth_method="bogus")  # type: ignore[arg-type]


class TestSplitKvPath:
    def test_with_data_segment(self) -> None:
        assert _split_kv_path("kv/data/foo") == ("kv", "foo")

    def test_with_nested_data_segment(self) -> None:
        assert _split_kv_path("custom/data/a/b/c") == ("custom", "a/b/c")

    def test_fallback_default_mount(self) -> None:
        assert _split_kv_path("foo/bar") == ("secret", "foo/bar")

    def test_empty_path(self) -> None:
        assert _split_kv_path("") == ("secret", "")


class TestKvV2:
    async def test_put_writes_and_returns_version(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.kv.v2.create_or_update_secret.return_value = {
            "data": {"version": 7}
        }
        v = await backend.put("kv/data/foo", b"sekret")
        assert v == 7
        call = mock_client.secrets.kv.v2.create_or_update_secret.call_args
        assert call.kwargs["path"] == "foo"
        assert call.kwargs["mount_point"] == "kv"
        assert call.kwargs["secret"] == {"value": "sekret"}

    async def test_get_returns_single_field_bytes(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": False,
            "initialized": True,
            "version": "1.x",
        }
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "hello"}}
        }
        out = await backend.get("kv/data/foo")
        assert out == b"hello"

    async def test_get_returns_json_when_multi_field(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        import json as _json

        mock_client.sys.read_health_status.return_value = {
            "sealed": False,
            "initialized": True,
            "version": "1.x",
        }
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"a": "1", "b": "2"}}
        }
        out = await backend.get("kv/data/foo")
        assert _json.loads(out.decode()) == {"a": "1", "b": "2"}

    async def test_get_passes_version_kwarg(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": False,
            "initialized": True,
            "version": "1.x",
        }
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "x"}}
        }
        await backend.get("kv/data/foo", version=3)
        call = mock_client.secrets.kv.v2.read_secret_version.call_args
        assert call.kwargs.get("version") == 3
        assert call.kwargs["path"] == "foo"
        assert call.kwargs["mount_point"] == "kv"

    async def test_versions_returns_sorted_int_list(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.kv.v2.read_secret_metadata.return_value = {
            "data": {"versions": {"3": {}, "1": {}, "2": {}}}
        }
        v = await backend.versions("kv/data/foo")
        assert v == [1, 2, 3]

    async def test_delete_calls_destroy_versions(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        await backend.delete("kv/data/foo", version=2)
        mock_client.secrets.kv.v2.destroy_secret_versions.assert_called_once()
        kw = mock_client.secrets.kv.v2.destroy_secret_versions.call_args.kwargs
        assert kw["path"] == "foo"
        assert kw["versions"] == [2]
        assert kw["mount_point"] == "kv"

    async def test_delete_metadata_when_no_version(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        await backend.delete("kv/data/foo")
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.assert_called_once()

    async def test_put_roundtrips_binary_via_latin1(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        """Arbitrary bytes (e.g. 0x00, 0xFF) survive put/get via latin1 encoding."""
        binary = bytes(range(256))
        mock_client.secrets.kv.v2.create_or_update_secret.return_value = {
            "data": {"version": 1}
        }
        await backend.put("kv/data/bin", binary)
        call = mock_client.secrets.kv.v2.create_or_update_secret.call_args
        stored_str = call.kwargs["secret"]["value"]
        assert stored_str.encode("latin1") == binary

        # Now simulate read of that stored str -- get() should recover bytes.
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": stored_str}}
        }
        out = await backend.get("kv/data/bin")
        assert out == binary

    async def test_put_raises_on_unexpected_response(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.kv.v2.create_or_update_secret.return_value = "weird"
        with pytest.raises(RuntimeError):
            await backend.put("kv/data/foo", b"x")

    async def test_get_raises_keyerror_on_invalid_path(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.kv.v2.read_secret_version.side_effect = (
            hvac.exceptions.InvalidPath("404")
        )
        with pytest.raises(KeyError):
            await backend.get("kv/data/missing")

    async def test_versions_raises_keyerror_on_invalid_path(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.kv.v2.read_secret_metadata.side_effect = (
            hvac.exceptions.InvalidPath("404")
        )
        with pytest.raises(KeyError):
            await backend.versions("kv/data/missing")

    async def test_delete_raises_keyerror_on_invalid_path(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.side_effect = (
            hvac.exceptions.InvalidPath("404")
        )
        with pytest.raises(KeyError):
            await backend.delete("kv/data/missing")

    async def test_versions_checks_unsealed(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": True,
            "initialized": True,
            "version": "1.x",
        }
        with pytest.raises(SealedError):
            await backend.versions("kv/data/foo")

    async def test_delete_checks_unsealed(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": True,
            "initialized": True,
            "version": "1.x",
        }
        with pytest.raises(SealedError):
            await backend.delete("kv/data/foo")

    async def test_health_check_caches_result(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        """Health check should be cached for the TTL window."""
        mock_client.sys.read_health_status.reset_mock()
        # First call hits backend
        await backend.health_check()
        # Subsequent calls within TTL should NOT re-hit
        await backend.health_check()
        await backend.health_check()
        assert mock_client.sys.read_health_status.call_count == 1


class TestTransitBase64:
    async def test_transit_sign_base64_encodes_input(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        import base64 as _b64

        mock_client.secrets.transit.sign_data.return_value = {
            "data": {"signature": "vault:v1:xx"}
        }
        payload = b"\x00\x01\x02hello\xff"
        await backend.transit_sign("k", payload)
        kw = mock_client.secrets.transit.sign_data.call_args.kwargs
        assert kw["hash_input"] == _b64.b64encode(payload).decode("ascii")


class TestSealed:
    async def test_get_raises_sealed_error_when_sealed(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": True,
            "initialized": True,
            "version": "1.x",
        }
        with pytest.raises(SealedError):
            await backend.get("kv/data/foo")

    async def test_put_raises_sealed_error_when_sealed(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": True,
            "initialized": True,
            "version": "1.x",
        }
        with pytest.raises(SealedError):
            await backend.put("kv/data/foo", b"x")


class TestTransit:
    async def test_transit_sign_returns_signature(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.secrets.transit.sign_data.return_value = {
            "data": {"signature": "vault:v1:abc"}
        }
        sig = await backend.transit_sign("mykey", b"payload")
        assert sig == "vault:v1:abc"
        kw = mock_client.secrets.transit.sign_data.call_args.kwargs
        assert kw["name"] == "mykey"
        assert kw["hash_algorithm"] == "sha2-256"


class TestLeaseAndHealth:
    async def test_renew_lease_invokes_sys(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        await backend.renew_lease("lease-id-1")
        mock_client.sys.renew_lease.assert_called_once_with(lease_id="lease-id-1")

    async def test_health_check_returns_dict(
        self, backend: VaultBackend, mock_client: MagicMock
    ) -> None:
        mock_client.sys.read_health_status.return_value = {
            "sealed": False,
            "initialized": True,
            "version": "1.15.0",
        }
        out = await backend.health_check()
        assert out == {"sealed": False, "initialized": True, "version": "1.15.0"}


# --------------------------------------------------------------------------- #
# Integration tests (skipped when vault binary missing)
# --------------------------------------------------------------------------- #


_VAULT_BIN = shutil.which("vault")


@pytest.fixture(scope="module")
def vault_dev_server() -> Iterator[str]:
    """Spawn ``vault server -dev`` and yield URL."""
    if not _VAULT_BIN:
        pytest.skip("vault binary missing")
    proc = subprocess.Popen(
        [
            _VAULT_BIN,
            "server",
            "-dev",
            "-dev-root-token-id=root",
            "-dev-listen-address=127.0.0.1:8201",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for readiness
    import urllib.request

    url = "http://127.0.0.1:8201"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}/v1/sys/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)
    try:
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.skipif(not _VAULT_BIN, reason="vault binary missing")
class TestVaultIntegration:
    async def test_kv_roundtrip(self, vault_dev_server: str) -> None:
        b = VaultBackend(url=vault_dev_server, auth_method="token", token="root")
        v = await b.put("secret/data/foo", b"hello")
        assert v >= 1
        out = await b.get("secret/data/foo")
        assert out == b"hello"

    async def test_versions(self, vault_dev_server: str) -> None:
        b = VaultBackend(url=vault_dev_server, auth_method="token", token="root")
        await b.put("secret/data/bar", b"v1")
        await b.put("secret/data/bar", b"v2")
        vs = await b.versions("secret/data/bar")
        assert len(vs) >= 2
        assert vs == sorted(vs)

    async def test_health_check_unsealed(self, vault_dev_server: str) -> None:
        b = VaultBackend(url=vault_dev_server, auth_method="token", token="root")
        h = await b.health_check()
        assert h["sealed"] is False
        assert h["initialized"] is True
