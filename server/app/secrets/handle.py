"""Secret handle for opaque token-based access to secrets."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class SecretHandle:
    """Opaque handle to a secret that can be revealed with re-auth.

    The handle itself does not contain the secret value. Use broker.reveal()
    to extract the plaintext, which requires fresh authentication.
    """

    id: str
    ref: Any  # SecretRef
    expires_at: datetime
    requester_id: str


@dataclass
class _HandleEntry:
    """Internal: entry stored in the handle store."""

    value: bytes
    ref: Any  # SecretRef
    requester_id: str
    expires_at: datetime


class HandleStore:
    """In-memory store for short-lived secret handles.

    Handles serve as opaque tokens pointing to cached secrets. Each handle
    is scoped to a requester and expires after a short TTL (default 60s).
    """

    def __init__(self) -> None:
        """Initialize handle store."""
        self._entries: dict[str, _HandleEntry] = {}

    def issue(
        self,
        ref: Any,
        value: bytes,
        requester: Any,
        expires_in_s: float = 60.0,
    ) -> SecretHandle:
        """Issue a new handle for a secret value.

        Args:
            ref: SecretRef the handle points to
            value: Secret value (bytes) to store temporarily
            requester: Requester object with user_id attribute
            expires_in_s: TTL in seconds (default 60)

        Returns:
            SecretHandle with opaque id
        """
        handle_id = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_s)

        self._entries[handle_id] = _HandleEntry(
            value=value,
            ref=ref,
            requester_id=requester.user_id,
            expires_at=expires_at,
        )

        return SecretHandle(
            id=handle_id,
            ref=ref,
            expires_at=expires_at,
            requester_id=requester.user_id,
        )

    def lookup(self, handle: SecretHandle, requester: Any) -> bytes | None:
        """Retrieve secret value from handle.

        Returns None if handle is expired, requester mismatch, or not found.
        Automatically deletes expired entries.

        Args:
            handle: SecretHandle to look up
            requester: Requester object with user_id attribute

        Returns:
            Secret value in bytes, or None if invalid/expired
        """
        entry = self._entries.get(handle.id)
        if entry is None:
            return None

        # Requester mismatch
        if entry.requester_id != requester.user_id:
            return None

        # Expired
        if datetime.now(timezone.utc) > entry.expires_at:
            self._entries.pop(handle.id, None)
            return None

        return entry.value

    def clear(self) -> None:
        """Clear all stored handles."""
        self._entries.clear()
