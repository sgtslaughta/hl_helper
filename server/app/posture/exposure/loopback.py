"""is_loopback: classify a bind address as loopback (not network-exposed)."""
from __future__ import annotations

import ipaddress


_LOOPBACK_NAMES = {"localhost"}


def is_loopback(addr: str) -> bool:
    """Return True if `addr` is a loopback bind that does NOT expose to network.

    Empty string and "0.0.0.0" / "::" mean INADDR_ANY (server-bound to ALL
    interfaces) — these are network-exposed, NOT loopback.
    """
    if addr in _LOOPBACK_NAMES:
        return True
    if not addr:
        return False
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_loopback
