"""Idempotency-key middleware.

Pattern: clients send `Idempotency-Key: <opaque>` on POST/PATCH/DELETE.
The middleware looks up `(principal_id, route, key)` in an in-memory store
with 24h TTL. On hit, returns the cached response without invoking the
downstream handler. On miss, invokes the handler and caches the response.

In-process only for now (single-replica deployments). C2 follow-up will
replace with DB-backed table for multi-replica safety.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_TTL = timedelta(hours=24)
HEADER = "Idempotency-Key"
WRITE_METHODS = frozenset({"POST", "PATCH", "DELETE"})


@dataclass
class _Entry:
    status_code: int
    body: bytes
    headers: dict[str, str]
    content_type: str
    expires_at: datetime


class IdempotencyStore:
    """Async-safe in-memory cache for idempotency entries."""

    def __init__(self, ttl: timedelta = DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._items: dict[tuple[str, str, str], _Entry] = {}

    async def get(self, principal_id: str, route: str, key: str,
                  now: datetime | None = None) -> _Entry | None:
        now = now or datetime.now(timezone.utc)
        async with self._lock:
            entry = self._items.get((principal_id, route, key))
            if entry is None:
                return None
            if now >= entry.expires_at:
                self._items.pop((principal_id, route, key), None)
                return None
            return entry

    async def put(self, principal_id: str, route: str, key: str,
                  *, status_code: int, body: bytes, headers: Mapping[str, str],
                  content_type: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        async with self._lock:
            self._items[(principal_id, route, key)] = _Entry(
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


def _principal_id(request: Request) -> str:
    """Best-effort principal identification.

    Until C3 wires real auth, fall back to a fixed sentinel so tests can
    still exercise the dedup path. Real auth must populate
    request.state.principal_id.
    """
    return getattr(request.state, "principal_id", "anonymous")


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replays cached response for repeated (principal, route, key) tuples.

    Only acts on WRITE_METHODS with the Idempotency-Key header. GET/HEAD/etc.
    bypass the middleware entirely.
    """

    def __init__(self, app: Any, *, store: IdempotencyStore | None = None) -> None:
        super().__init__(app)
        self.store = store or IdempotencyStore()

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Response:
        if request.method not in WRITE_METHODS:
            return cast(Response, await call_next(request))
        key = request.headers.get(HEADER)
        if not key:
            return cast(Response, await call_next(request))

        principal_id = _principal_id(request)
        route = request.url.path

        cached = await self.store.get(principal_id, route, key)
        if cached is not None:
            return Response(
                content=cached.body,
                status_code=cached.status_code,
                headers=cached.headers,
                media_type=cached.content_type,
            )

        # Miss: invoke handler, capture response
        response = cast(Response, await call_next(request))
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk
        await self.store.put(
            principal_id, route, key,
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
