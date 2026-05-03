"""Tests for rate limiter LRU + XFF policy."""


from server.app.api.middleware.rate_limit import RateLimiter


def test_rate_limiter_lru_eviction():
    """Bucket count never exceeds max_buckets; oldest evicted first."""
    limiter = RateLimiter(rate_per_sec=10.0, burst=100, max_buckets=3)

    # Fill up to max
    limiter.check("ip1")
    limiter.check("ip2")
    limiter.check("ip3")
    assert len(limiter._buckets) == 3

    # Add one more → ip1 should be evicted
    limiter.check("ip4")
    assert len(limiter._buckets) == 3
    assert "ip1" not in limiter._buckets
    assert "ip2" in limiter._buckets
    assert "ip3" in limiter._buckets
    assert "ip4" in limiter._buckets


def test_rate_limiter_xff_trusted_proxy():
    """Trusted proxy IPs use X-Forwarded-For rightmost hop."""
    limiter = RateLimiter(rate_per_sec=10.0, burst=1, trusted_proxy_ips=["127.0.0.1"])

    # Simulate request from proxy with X-Forwarded-For
    key = limiter.extract_client_ip(
        client_host="127.0.0.1",  # proxy IP
        xff_header="10.0.0.1, 10.0.0.2"  # rightmost is 10.0.0.2
    )
    assert key == "10.0.0.2"


def test_rate_limiter_xff_untrusted_proxy():
    """Untrusted proxy IP ignores X-Forwarded-For."""
    limiter = RateLimiter(rate_per_sec=10.0, burst=1, trusted_proxy_ips=["127.0.0.1"])

    # Request from untrusted IP
    key = limiter.extract_client_ip(
        client_host="203.0.113.1",  # not in trusted list
        xff_header="10.0.0.1, 10.0.0.2"
    )
    assert key == "203.0.113.1"  # use client_host, ignore XFF


def test_rate_limiter_no_xff_falls_back():
    """Missing X-Forwarded-For falls back to client.host even when proxy trusted."""
    limiter = RateLimiter(rate_per_sec=10.0, burst=1, trusted_proxy_ips=["127.0.0.1"])

    key = limiter.extract_client_ip(
        client_host="127.0.0.1",
        xff_header=None
    )
    assert key == "127.0.0.1"


def test_rate_limiter_xff_empty_falls_back():
    """Empty/malformed X-Forwarded-For falls back to client.host."""
    limiter = RateLimiter(rate_per_sec=10.0, burst=1, trusted_proxy_ips=["127.0.0.1"])

    key = limiter.extract_client_ip(
        client_host="127.0.0.1",
        xff_header=""
    )
    assert key == "127.0.0.1"
