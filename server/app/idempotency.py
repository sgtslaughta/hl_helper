"""Idempotency-key middleware.

Pattern: clients send `Idempotency-Key: <opaque>` on POST/PATCH/DELETE.
The middleware looks up `(principal_id, route, key)` in an in-memory store
with 24h TTL. On hit, returns the cached response without invoking the
downstream handler. On miss, invokes the handler and caches the response.

Caching policy:
- Only 2xx/3xx responses are cached. 4xx/5xx are returned but not stored,
  on the assumption that the client may retry with intent to succeed.
- Requests without an authenticated principal (principal_id == "anonymous")
  are NOT cached (fail-closed; prevents cross-request response leakage).
- Concurrent requests with the same (principal, route, key) serialize:
  the first acquires the slot and invokes the handler; subsequent requests
  wait for completion and use the cached result.

Limitations:
- Caches buffer the entire response body in memory. StreamingResponse
  and FileResponse are not safe; routes returning these should not use
  Idempotency-Key (or should be excluded from this middleware).
- In-process only for now (single-replica deployments). C2 follow-up will
  replace with DB-backed table for multi-replica safety.
"""
from __future__ import annotations
import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_TTL = timedelta(hours=24)
HEADER = "Idempotency-Key"
WRITE_METHODS = frozenset({"POST", "PATCH", "DELETE"})
ANONYMOUS = "anonymous"


@dataclass
class _Entry:
    status_code: int
    body: bytes
    headers: dict[str, str]
    content_type: str
    expires_at: datetime


class IdempotencyStore:
    """Async-safe in-memory cache for idempotency entries."""

    def __init__(self, ttl: timedelta = DEFAULT_TTL, *, max_entries: int = 10000, max_body_bytes: int = 1_048_576) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._max_body_bytes = max_body_bytes
        self._lock = asyncio.Lock()
        self._items: OrderedDict[tuple[str, str, str, str], _Entry] = OrderedDict()
        self._inflight: dict[tuple[str, str, str, str], asyncio.Event] = {}

    async def get(self, principal_id: str, route: str, key: str, body_hash: str,
                  now: datetime | None = None) -> _Entry | None:
        now = now or datetime.now(timezone.utc)
        async with self._lock:
            entry = self._items.get((principal_id, route, key, body_hash))
            if entry is None:
                return None
            if now >= entry.expires_at:
                self._items.pop((principal_id, route, key, body_hash), None)
                return None
            # Move to end to maintain LRU order
            self._items.move_to_end((principal_id, route, key, body_hash))
            return entry

    async def put(self, principal_id: str, route: str, key: str, body_hash: str,
                  *, status_code: int, body: bytes, headers: Mapping[str, str],
                  content_type: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        async with self._lock:
            # Evict oldest entry if at capacity
            if len(self._items) >= self._max:
                self._items.popitem(last=False)
            self._items[(principal_id, route, key, body_hash)] = _Entry(
                status_code=status_code, body=body,
                headers=dict(headers), content_type=content_type,
                expires_at=now + self._ttl,
            )

    async def purge_expired(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        async with self._lock:
            stale = [k for k, v in self._items.items() if now >= v.expires_at]
            for k in stale:
                self._items.pop(k, None)
            return len(stale)

    async def acquire_or_wait(self, key: tuple[str, str, str, str]) -> bool:
        """Return True if caller should run the handler (we own the slot);
        return False if another request is already running and we should wait
        for its result."""
        async with self._lock:
            if key in self._inflight:
                ev = self._inflight[key]
                # Release lock before waiting
            else:
                ev = asyncio.Event()
                self._inflight[key] = ev
                return True
        await ev.wait()
        return False

    async def release(self, key: tuple[str, str, str, str]) -> None:
        async with self._lock:
            ev = self._inflight.pop(key, None)
            if ev is not None:
                ev.set()

    async def check_conflict(self, principal_id: str, route: str, key: str, body_hash: str) -> str | None:
        """Check if same (principal, route, key) exists with different body_hash.
        Return the conflicting body_hash if found, None otherwise."""
        async with self._lock:
            for (p, r, k, bh), entry in self._items.items():
                if p == principal_id and r == route and k == key and bh != body_hash:
                    # Found a conflict
                    return bh
        return None


def _principal_id(request: Request) -> str:
    """Best-effort principal identification.

    Until C3 wires real auth, fall back to a fixed sentinel so tests can
    still exercise the dedup path. Real auth must populate
    request.state.principal_id.
    """
    return getattr(request.state, "principal_id", ANONYMOUS)


def _from_entry(entry: _Entry) -> Response:
    """Build a Response from a cached _Entry."""
    return Response(
        content=entry.body,
        status_code=entry.status_code,
        headers=entry.headers,
        media_type=entry.content_type,
    )


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replays cached response for repeated (principal, route, key) tuples.

    Only acts on WRITE_METHODS with the Idempotency-Key header. GET/HEAD/etc.
    bypass the middleware entirely.
    """

    def __init__(self, app: Any, *, store: IdempotencyStore | None = None, max_body_bytes: int | None = None) -> None:
        super().__init__(app)
        # Resolve effective max body bytes: explicit arg wins; else inherit from
        # provided store; else use a 1 MiB default.
        if max_body_bytes is None and store is not None:
            max_body_bytes = store._max_body_bytes
        if max_body_bytes is None:
            max_body_bytes = 1_048_576
        self.store = store or IdempotencyStore(max_body_bytes=max_body_bytes)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Response:
        if request.method not in WRITE_METHODS:
            return cast(Response, await call_next(request))
        key = request.headers.get(HEADER)
        if not key:
            return cast(Response, await call_next(request))

        principal_id = _principal_id(request)
        # Fix 1: Skip caching for anonymous principals (fail-closed)
        if principal_id == ANONYMOUS:
            return cast(Response, await call_next(request))

        route = request.url.path

        # Compute body hash from request body
        request_body = await request.body()

        # Check body size limit
        if len(request_body) > self.max_body_bytes:
            from server.app.errors import problem
            return problem(
                413,
                "payload_too_large",
                title="Payload Too Large",
                detail=f"request body exceeds {self.max_body_bytes} bytes",
            )

        body_hash = hashlib.sha256(request_body).hexdigest()
        key_tuple = (principal_id, route, key, body_hash)

        # Check for conflicting body_hash with same (principal, route, key)
        conflict = await self.store.check_conflict(principal_id, route, key, body_hash)
        if conflict is not None:
            from server.app.errors import problem
            return problem(
                409,
                "idempotency_key_conflict",
                title="Conflict",
                detail="request with same idempotency key but different body already exists",
            )

        # Check cache first
        cached = await self.store.get(principal_id, route, key, body_hash)
        if cached is not None:
            return _from_entry(cached)

        # Fix 2: Serialize concurrent requests with same key
        owner = await self.store.acquire_or_wait(key_tuple)
        if not owner:
            # Other request finished; read cached result
            cached = await self.store.get(principal_id, route, key, body_hash)
            if cached is not None:
                return _from_entry(cached)
            # Other request didn't cache (e.g., it errored before put). Fall through.

        try:
            # Miss: invoke handler, capture response
            response = cast(Response, await call_next(request))
            body = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body += chunk

            # Fix 4: Only cache 2xx/3xx responses
            if response.status_code < 400:
                await self.store.put(
                    principal_id, route, key, body_hash,
                    status_code=response.status_code,
                    body=body,
                    headers={k: v for k, v in response.headers.items()
                             if k.lower() not in {"content-length"}},
                    content_type=response.headers.get("content-type", "application/json"),
                )

            return Response(
                content=body, status_code=response.status_code,
                headers=dict(response.headers), media_type=response.media_type,
            )
        finally:
            await self.store.release(key_tuple)
