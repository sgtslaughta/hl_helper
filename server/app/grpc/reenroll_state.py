"""ReEnroll in-memory state: nonce cache + rate limiter."""
from __future__ import annotations

import hashlib
import hmac
import time
from collections import deque
from threading import Lock
from typing import Deque

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


class NonceCache:
    """One-shot nonces per host_id. Expires after ttl_seconds."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[bytes, float]] = {}
        self._lock = Lock()

    def put(self, host_id: str, nonce: bytes) -> None:
        with self._lock:
            self._entries[host_id] = (nonce, time.monotonic())

    def consume(self, host_id: str, nonce: bytes) -> bool:
        with self._lock:
            entry = self._entries.get(host_id)
            if entry is None:
                return False
            stored, ts = entry
            if time.monotonic() - ts > self._ttl:
                self._entries.pop(host_id, None)
                return False
            if not hmac.compare_digest(stored, nonce):
                return False
            self._entries.pop(host_id, None)
            return True


class ReEnrollRateLimiter:
    """Sliding-window rate limiter. Default: 3 attempts per 24h per host."""

    def __init__(
        self,
        *,
        window_seconds: float = 86400.0,
        max_per_window: int = 3,
    ) -> None:
        self._window = window_seconds
        self._max = max_per_window
        self._events: dict[str, Deque[float]] = {}
        self._lock = Lock()

    def allow(self, host_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(host_id, deque())
            cutoff = now - self._window
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self._max:
                return False
            events.append(now)
            return True


def canonical_reenroll_payload(
    host_id: str, nonce: bytes, ts_unix: int
) -> bytes:
    """Domain-separated message bytes for signing/verification."""
    body = (
        b"reenroll-v1|"
        + host_id.encode()
        + b"|"
        + nonce
        + b"|"
        + str(ts_unix).encode()
    )
    return hashlib.sha256(body).digest()


def verify_reenroll_signature(
    *,
    host_id: str,
    nonce: bytes,
    ts_unix: int,
    signature: bytes,
    signing_pubkey: bytes,
) -> bool:
    """Verify Ed25519 signature over canonical payload."""
    try:
        pk = ed25519.Ed25519PublicKey.from_public_bytes(signing_pubkey)
    except Exception:
        return False
    try:
        pk.verify(signature, canonical_reenroll_payload(host_id, nonce, ts_unix))
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False
