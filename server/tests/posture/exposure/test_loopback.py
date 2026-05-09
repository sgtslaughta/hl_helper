"""Tests for is_loopback() helper."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "addr,expected",
    [
        ("127.0.0.1", True),
        ("127.255.255.254", True),
        ("::1", True),
        ("localhost", True),
        ("0.0.0.0", False),    # INADDR_ANY = exposed
        ("::", False),          # ipv6 any = exposed
        ("", False),            # empty = exposed (server-bound to ANY)
        ("192.168.1.10", False),
        ("10.0.0.1", False),
        ("169.254.0.1", False),
    ],
)
def test_is_loopback(addr, expected):
    from server.app.posture.exposure.loopback import is_loopback

    assert is_loopback(addr) is expected
