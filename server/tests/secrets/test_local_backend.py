"""Tests for LocalEncryptedFileBackend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterator

import pytest

from server.app.secrets.backends.local import LocalEncryptedFileBackend
from server.app.secrets.backends.base import IntegrityError


@pytest.fixture
async def local_backend(tmp_path: Path) -> AsyncIterator[LocalEncryptedFileBackend]:
    """Create a LocalEncryptedFileBackend with temp directory."""
    root_key = os.urandom(32)
    backend = LocalEncryptedFileBackend(tmp_path, root_key)
    yield backend


class TestLocalBackendPutGet:
    """Tests for basic put/get roundtrip."""

    async def test_put_get_roundtrip(self, local_backend: LocalEncryptedFileBackend) -> None:
        """Put and get return same value."""
        await local_backend.put("foo", b"value")
        result = await local_backend.get("foo")
        assert result == b"value"

    async def test_get_nonexistent_raises(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Getting nonexistent secret raises KeyError."""
        with pytest.raises(KeyError):
            await local_backend.get("nonexistent")

    async def test_multiple_secrets_independent(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Multiple secrets are stored and retrieved independently."""
        await local_backend.put("secret1", b"value1")
        await local_backend.put("secret2", b"value2")
        assert await local_backend.get("secret1") == b"value1"
        assert await local_backend.get("secret2") == b"value2"


class TestLocalBackendVersioning:
    """Tests for versioning behavior."""

    async def test_versioning_retains_last_10(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Writing 15 versions retains only last 10."""
        for i in range(15):
            await local_backend.put("foo", f"v{i}".encode())
        versions = await local_backend.versions("foo")
        assert len(versions) == 10
        # Versions should be sorted in ascending order
        assert versions == sorted(versions)
        # Latest version should be 14 (0-indexed from 15 writes)
        assert max(versions) == 15

    async def test_put_returns_version(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Put returns the version number."""
        v1 = await local_backend.put("foo", b"first")
        v2 = await local_backend.put("foo", b"second")
        assert v2 == v1 + 1

    async def test_versions_nonexistent_raises(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Versions of nonexistent secret raises KeyError."""
        with pytest.raises(KeyError):
            await local_backend.versions("nonexistent")

    async def test_get_latest_after_multiple_puts(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Get returns latest version after multiple puts."""
        await local_backend.put("foo", b"v0")
        await local_backend.put("foo", b"v1")
        await local_backend.put("foo", b"v2")
        result = await local_backend.get("foo")
        assert result == b"v2"


class TestLocalBackendIntegrity:
    """Tests for AEAD tamper detection."""

    async def test_aead_tamper_detected(
        self, local_backend: LocalEncryptedFileBackend, tmp_path: Path
    ) -> None:
        """Flipping a byte in ciphertext raises IntegrityError."""
        await local_backend.put("foo", b"x" * 64)
        fpath = local_backend._path("foo", version=1)
        blob = fpath.read_bytes()
        corrupted = blob[:50] + bytes([blob[50] ^ 1]) + blob[51:]
        fpath.write_bytes(corrupted)
        # Attempting to decrypt should raise IntegrityError
        with pytest.raises(IntegrityError):
            await local_backend.get("foo")

    async def test_tamper_nonce_raises(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Flipping a byte in nonce raises IntegrityError."""
        await local_backend.put("foo", b"value")
        fpath = local_backend._path("foo", version=1)
        blob = fpath.read_bytes()
        # Flip a bit in nonce (first 12 bytes)
        corrupted = bytes([blob[0] ^ 1]) + blob[1:]
        fpath.write_bytes(corrupted)
        with pytest.raises(IntegrityError):
            await local_backend.get("foo")


class TestLocalBackendPermissions:
    """Tests for directory permissions."""

    async def test_perms_enforced(
        self, local_backend: LocalEncryptedFileBackend, tmp_path: Path
    ) -> None:
        """Root secrets directory has 0o700 permissions."""
        await local_backend.put("foo", b"v")
        secrets_dir = tmp_path / ".secrets"
        info = secrets_dir.stat()
        # Extract last 3 octal digits from mode
        perms = oct(info.st_mode)[-3:]
        assert perms == "700"

    async def test_perms_preserved_on_put(
        self, local_backend: LocalEncryptedFileBackend, tmp_path: Path
    ) -> None:
        """Directory permissions remain 0o700 after multiple puts."""
        await local_backend.put("foo", b"v1")
        await local_backend.put("foo", b"v2")
        secrets_dir = tmp_path / ".secrets"
        info = secrets_dir.stat()
        perms = oct(info.st_mode)[-3:]
        assert perms == "700"


class TestLocalBackendConcurrency:
    """Tests for concurrent put behavior."""

    async def test_concurrent_put_monotonic_versions(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """Concurrent puts produce monotonically increasing versions."""
        import asyncio

        results = await asyncio.gather(
            local_backend.put("foo", b"v1"),
            local_backend.put("foo", b"v2"),
            local_backend.put("foo", b"v3"),
        )
        # All three should complete successfully with different versions
        assert len(set(results)) == 3
        assert all(isinstance(v, int) for v in results)


class TestLocalBackendPathTraversal:
    """Tests for path traversal rejection."""

    async def test_reject_path_with_dotdot(self, local_backend: LocalEncryptedFileBackend) -> None:
        """Reject paths containing .. segments."""
        with pytest.raises(ValueError, match="invalid path"):
            await local_backend.put("foo/../bar", b"value")

    async def test_reject_path_with_dot_segment(self, local_backend: LocalEncryptedFileBackend) -> None:
        """Reject paths containing . segment."""
        with pytest.raises(ValueError, match="invalid path"):
            await local_backend.put("foo/./bar", b"value")

    async def test_reject_path_leading_slash(self, local_backend: LocalEncryptedFileBackend) -> None:
        """Reject paths starting with /."""
        with pytest.raises(ValueError, match="invalid path"):
            await local_backend.put("/foo", b"value")

    async def test_reject_path_invalid_chars(self, local_backend: LocalEncryptedFileBackend) -> None:
        """Reject paths with invalid characters."""
        with pytest.raises(ValueError, match="invalid path"):
            await local_backend.put("foo@bar", b"value")

    async def test_accept_valid_path_chars(self, local_backend: LocalEncryptedFileBackend) -> None:
        """Accept paths with alphanumerics, underscore, dash, dot, slash."""
        version = await local_backend.put("foo_bar-baz.qux/nested", b"value")
        assert version == 1
        result = await local_backend.get("foo_bar-baz.qux/nested")
        assert result == b"value"


class TestLocalBackendFilePermissions:
    """Tests for file and directory permissions."""

    async def test_secret_file_perms_0o600(
        self, local_backend: LocalEncryptedFileBackend, tmp_path: Path
    ) -> None:
        """Secret files are stored with 0o600 permissions."""
        await local_backend.put("foo", b"value")
        fpath = local_backend._path("foo", version=1)
        info = fpath.stat()
        perms = oct(info.st_mode)[-3:]
        assert perms == "600"


class TestLocalBackendInvalidTag:
    """Tests for InvalidTag exception handling."""

    async def test_invalid_tag_raises_integrity_error(
        self, local_backend: LocalEncryptedFileBackend
    ) -> None:
        """InvalidTag from decrypt raises IntegrityError, not generic Exception."""
        await local_backend.put("foo", b"value")
        fpath = local_backend._path("foo", version=1)
        blob = fpath.read_bytes()
        # Corrupt the tag (last 16 bytes)
        corrupted = blob[:-16] + b"x" * 16
        fpath.write_bytes(corrupted)
        with pytest.raises(IntegrityError):
            await local_backend.get("foo")
