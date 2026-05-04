"""LRU cache with TTL for broker caching."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class BrokerCache:
    """LRU cache with per-entry TTL for secret values.

    Tracks hit/miss counters for testing and monitoring.
    """

    def __init__(self, ttl_seconds: int = 30) -> None:
        """Initialize broker cache.

        Args:
            ttl_seconds: Default TTL for cached entries
        """
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[bytes, datetime]] = {}
        self.hits = 0
        self.misses = 0

    def _cache_key(self, ref: Any) -> str:
        """Generate cache key from SecretRef."""
        return str(ref)

    def get(self, ref: Any) -> bytes | None:
        """Retrieve value from cache if not expired.

        Args:
            ref: SecretRef to look up

        Returns:
            Cached value in bytes, or None if not found or expired
        """
        key = self._cache_key(ref)
        entry = self._entries.get(key)

        if entry is None:
            self.misses += 1
            return None

        value, expires_at = entry

        # Expired
        if datetime.now(timezone.utc) > expires_at:
            self._entries.pop(key, None)
            self.misses += 1
            return None

        self.hits += 1
        return value

    def put(self, ref: Any, value: bytes, ttl_s: int | float) -> None:
        """Cache a secret value with TTL.

        Args:
            ref: SecretRef to cache
            value: Secret value in bytes
            ttl_s: TTL in seconds
        """
        key = self._cache_key(ref)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_s)
        self._entries[key] = (value, expires_at)

    def invalidate(self, ref: Any) -> None:
        """Remove specific ref from cache.

        Args:
            ref: SecretRef to invalidate
        """
        key = self._cache_key(ref)
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._entries.clear()
