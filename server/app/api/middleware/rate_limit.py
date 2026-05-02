"""In-memory token-bucket rate limiter for per-IP rate limiting."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status


@dataclass
class _Bucket:
    """Token bucket state."""

    tokens: float
    last: float


class RateLimiter:
    """In-memory token-bucket rate limiter keyed by client IP.

    Not suitable for HA — single-process only. C12 will replace with Redis-backed limiter.
    """

    def __init__(self, *, rate_per_sec: float = 1.0, burst: int = 5) -> None:
        """Initialize rate limiter.

        Args:
            rate_per_sec: Tokens added per second.
            burst: Maximum tokens in bucket.
        """
        self.rate_per_sec = rate_per_sec
        self.burst = burst
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    def check(self, key: str, *, now: float | None = None) -> None:
        """Check and consume one token, raise HTTPException(429) if over limit.

        Args:
            key: Rate limit key (e.g., IP address).
            now: Current time (for testing). Defaults to time.time().

        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded.
        """
        if now is None:
            now = time.time()

        with self._lock:
            # Get or create bucket
            if key not in self._buckets:
                self._buckets[key] = _Bucket(tokens=float(self.burst), last=now)
            else:
                bucket = self._buckets[key]
                # Refill tokens based on elapsed time
                elapsed = now - bucket.last
                bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate_per_sec)
                bucket.last = now

            bucket = self._buckets[key]

            # Check if we have tokens
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
            else:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="rate limit exceeded",
                )


def rate_limit_dependency(limiter: RateLimiter) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency that rate-limits by request.client.host.

    Args:
        limiter: RateLimiter instance to use.

    Returns:
        Dependency function for FastAPI Depends.
    """

    async def _rate_limit(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        limiter.check(client_host)

    return _rate_limit
