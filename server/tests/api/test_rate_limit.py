"""Tests for rate limiting."""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException, status

from server.app.api.middleware.rate_limit import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_limiter_allows_burst(self) -> None:
        """Verify burst capacity allows initial requests."""
        limiter = RateLimiter(rate_per_sec=1.0, burst=3)
        now = time.time()

        # First 3 requests should succeed
        for _ in range(3):
            limiter.check("key1", now=now)

        # 4th request should fail
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("key1", now=now)
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_limiter_refills(self) -> None:
        """Verify tokens refill over time."""
        limiter = RateLimiter(rate_per_sec=1.0, burst=3)
        now = time.time()

        # Exhaust burst
        for _ in range(3):
            limiter.check("key1", now=now)

        # Should fail immediately
        with pytest.raises(HTTPException):
            limiter.check("key1", now=now)

        # Advance time by 2 seconds (should gain 2 tokens)
        now_later = now + 2.0
        limiter.check("key1", now=now_later)  # Use 1 token
        limiter.check("key1", now=now_later)  # Use 1 token

        # Should fail on 3rd request at same time
        with pytest.raises(HTTPException):
            limiter.check("key1", now=now_later)

    def test_limiter_per_key_isolation(self) -> None:
        """Verify different keys have separate buckets."""
        limiter = RateLimiter(rate_per_sec=1.0, burst=2)
        now = time.time()

        # Exhaust key1
        limiter.check("key1", now=now)
        limiter.check("key1", now=now)

        # key2 should still have capacity
        limiter.check("key2", now=now)
        limiter.check("key2", now=now)

    def test_limiter_under_rate_always_passes(self) -> None:
        """Verify requests under rate limit always pass."""
        limiter = RateLimiter(rate_per_sec=10.0, burst=100)
        now = time.time()

        # Make 50 requests spaced 0.05s apart (5 per second, under 10/sec limit)
        for i in range(50):
            current_time = now + (i * 0.05)
            limiter.check("key1", now=current_time)
