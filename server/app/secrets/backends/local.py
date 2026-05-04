"""Local encrypted file backend for secrets."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from server.app.secrets.backends.base import IntegrityError


class LocalEncryptedFileBackend:
    """Encrypted file-based secrets backend with per-secret AES-256-GCM keys."""

    def __init__(self, root: Path, root_key: bytes) -> None:
        """Initialize backend.

        Args:
            root: Root directory for secrets storage
            root_key: Master key for HKDF derivation (recommend 32 bytes)
        """
        self.root = root
        self.root_key = root_key
        self._lock = asyncio.Lock()

    def _validate_path(self, path: str) -> None:
        """Validate path against traversal and injection attacks.

        Args:
            path: Secret path to validate

        Raises:
            ValueError: If path is invalid
        """
        if not path:
            raise ValueError("invalid path")

        # Check path format: alphanumeric start, then alphanumeric, underscore, dash, dot, slash
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$", path):
            raise ValueError("invalid path")

        # Check for .. and . segments
        segments = path.split("/")
        for segment in segments:
            if segment in ("..", "."):
                raise ValueError("invalid path")

    @property
    def _secrets_dir(self) -> Path:
        """Get or create .secrets subdirectory with 0o700 permissions."""
        secrets_dir = self.root / ".secrets"
        if not secrets_dir.exists():
            secrets_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            # Override umask and correct loose perms
            os.chmod(str(secrets_dir), 0o700)
        return secrets_dir

    def _path(self, path: str, version: int) -> Path:
        """Get file path for secret version."""
        return self._secrets_dir / f"{path}.v{version}.bin"

    def _derive_key(self, path: str) -> bytes:
        """Derive per-secret AES-256 key from root key using HKDF-SHA256.

        Uses fixed salt "hlh-secrets-v1" for domain separation and versioning.
        Info contains path as domain separator.

        Args:
            path: Secret path used as HKDF info

        Returns:
            32-byte AES-256 key
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"hlh-secrets-v1",
            info=b"hlh-secrets-key:" + path.encode("utf-8"),
        )
        return hkdf.derive(self.root_key)

    async def _get_next_version(self, path: str) -> int:
        """Find next version number for a secret."""
        versions = []
        for f in self._secrets_dir.glob(f"{path}.v*.bin"):
            match = re.match(r"^(?P<name>.+)\.v(?P<ver>\d+)\.bin$", f.name)
            if match:
                versions.append(int(match.group("ver")))
        versions.sort()
        return versions[-1] + 1 if versions else 1

    async def _cleanup_old_versions(self, path: str) -> None:
        """Keep only the last 10 versions of a secret."""
        files_with_versions = []
        for f in self._secrets_dir.glob(f"{path}.v*.bin"):
            match = re.match(r"^(?P<name>.+)\.v(?P<ver>\d+)\.bin$", f.name)
            if match:
                files_with_versions.append((f, int(match.group("ver"))))
        files_with_versions.sort(key=lambda x: x[1])
        for old_file, _ in files_with_versions[:-10]:
            old_file.unlink()

    async def get(self, path: str, version: int | None = None) -> bytes:
        """Retrieve secret from latest version (or a specific version if requested).

        Args:
            path: Secret path
            version: Optional specific version. If ``None``, returns latest.

        Returns:
            Decrypted secret value

        Raises:
            KeyError: If secret (or requested version) not found
            IntegrityError: If AEAD verification fails
        """
        self._validate_path(path)
        versions = await self.versions(path)

        if version is None:
            version = versions[-1]
        elif version not in versions:
            raise KeyError(f"Secret version not found: {path} v{version}")
        try:
            fpath = self._path(path, version)
            blob = fpath.read_bytes()
            nonce = blob[:12]
            ciphertext_with_tag = blob[12:]
            key = self._derive_key(path)
            cipher = AESGCM(key)
            plaintext = cipher.decrypt(nonce, ciphertext_with_tag, None)
            return plaintext
        except InvalidTag as e:
            raise IntegrityError(f"AEAD verification failed: {e}") from e

    async def put(self, path: str, value: bytes) -> int:
        """Store secret with new version.

        Args:
            path: Secret path
            value: Secret value as bytes

        Returns:
            Version number
        """
        self._validate_path(path)
        async with self._lock:
            next_version = await self._get_next_version(path)
            key = self._derive_key(path)
            nonce = os.urandom(12)
            cipher = AESGCM(key)
            ciphertext = cipher.encrypt(nonce, value, None)
            payload = nonce + ciphertext
            fpath = self._path(path, next_version)
            fpath.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = fpath.parent / f"{fpath.name}.tmp"

            # Atomic write with proper fsync
            fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)

            os.replace(str(tmp_path), str(fpath))

            # Fsync directory
            parent_dir = str(fpath.parent)
            dir_fd = os.open(parent_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

            # Guarantee file mode is 0o600
            os.chmod(str(fpath), 0o600)

            await self._cleanup_old_versions(path)
            return next_version

    async def versions(self, path: str) -> list[int]:
        """List all stored versions of a secret.

        Args:
            path: Secret path

        Returns:
            List of version numbers in ascending order

        Raises:
            KeyError: If no versions found
        """
        self._validate_path(path)
        versions = []
        for f in self._secrets_dir.glob(f"{path}.v*.bin"):
            match = re.match(r"^(?P<name>.+)\.v(?P<ver>\d+)\.bin$", f.name)
            if match:
                versions.append(int(match.group("ver")))
        versions.sort()
        if not versions:
            raise KeyError(f"Secret not found: {path}")
        return versions

    async def delete(self, path: str, version: int | None = None) -> None:
        """Delete a secret.

        Args:
            path: Secret path
            version: Optional specific version to delete. If ``None``,
                deletes all versions of the secret.
        """
        self._validate_path(path)
        async with self._lock:
            if version is None:
                for f in self._secrets_dir.glob(f"{path}.v*.bin"):
                    f.unlink()
            else:
                fpath = self._path(path, version)
                if fpath.exists():
                    fpath.unlink()

    async def enumerate_paths(self) -> list[str]:
        """Enumerate all secret paths stored in backend.

        Walks the .secrets directory, extracts unique secret paths from
        versioned filenames (e.g., 'foo.v1.bin' -> 'foo').

        Returns:
            List of unique secret paths
        """
        if not self._secrets_dir.exists():
            return []

        paths: set[str] = set()
        for f in self._secrets_dir.glob("*.v*.bin"):
            match = re.match(r"^(?P<name>.+)\.v(?P<ver>\d+)\.bin$", f.name)
            if match:
                paths.add(match.group("name"))

        return sorted(list(paths))
