"""In-memory token-bucket rate limiter for per-IP rate limiting."""

from __future__ import annotations

import time
from collections import OrderedDict
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

    def __init__(self, *, rate_per_sec: float = 1.0, burst: int = 5,
                 max_buckets: int = 100_000, trusted_proxy_ips: list[str] | None = None) -> None:
        """Initialize rate limiter.

        Args:
            rate_per_sec: Tokens added per second.
            burst: Maximum tokens in bucket.
            max_buckets: Maximum number of buckets before LRU eviction.
            trusted_proxy_ips: List of IP addresses that are trusted proxies (for X-Forwarded-For).
        """
        self.rate_per_sec = rate_per_sec
        self.burst = burst
        self.max_buckets = max_buckets
        self.trusted_proxy_ips = set(trusted_proxy_ips or [])
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = Lock()

    def extract_client_ip(self, client_host: str, xff_header: str | None = None) -> str:
        """Extract client IP from client_host or X-Forwarded-For if trusted proxy.

        Args:
            client_host: The client's host IP (from request.client.host).
            xff_header: X-Forwarded-For header value if present.

        Returns:
            The client IP to use for rate limiting.
        """
        # If client_host is in trusted_proxy_ips, parse XFF
        if client_host in self.trusted_proxy_ips and xff_header:
            # Parse X-Forwarded-For: rightmost hop is the most recent proxy
            ips = [ip.strip() for ip in xff_header.split(",")]
            if ips and ips[-1]:  # Get rightmost, non-empty
                return ips[-1]
        # Fall back to client_host
        return client_host

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
                # Evict oldest bucket if at capacity
                if len(self._buckets) >= self.max_buckets:
                    self._buckets.popitem(last=False)
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
    """FastAPI dependency that rate-limits by client IP (with X-Forwarded-For support).

    Args:
        limiter: RateLimiter instance to use.

    Returns:
        Dependency function for FastAPI Depends.
    """

    async def _rate_limit(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        xff_header = request.headers.get("X-Forwarded-For")
        key = limiter.extract_client_ip(client_host, xff_header)
        limiter.check(key)

    return _rate_limit
