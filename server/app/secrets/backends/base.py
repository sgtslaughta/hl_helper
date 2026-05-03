"""Base protocol for secrets backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class IntegrityError(Exception):
    """Raised when AEAD verification fails."""

    pass


@runtime_checkable
class SecretsBackend(Protocol):
    """Protocol for secrets backends."""

    async def get(self, path: str) -> bytes:
        """Retrieve secret value by path.

        Args:
            path: Secret path

        Returns:
            Secret value as bytes

        Raises:
            KeyError: If secret not found
            IntegrityError: If AEAD verification fails
        """
        ...

    async def put(self, path: str, value: bytes) -> int:
        """Store secret value and return version number.

        Args:
            path: Secret path
            value: Secret value as bytes

        Returns:
            Version number (incremented on each write)
        """
        ...

    async def versions(self, path: str) -> list[int]:
        """List all available versions for a secret.

        Args:
            path: Secret path

        Returns:
            List of version numbers in ascending order

        Raises:
            KeyError: If secret not found
        """
        ...

    async def delete(self, path: str) -> None:
        """Delete all versions of a secret.

        Args:
            path: Secret path
        """
        ...
