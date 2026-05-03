"""Per-event RBAC visibility filter for WebSocket subscribers."""

from __future__ import annotations

from server.app.events.bus import Event


def event_visible(principal: str, event: Event) -> bool:
    """Check if event is visible to principal based on payload.

    Args:
        principal: Principal identifier ("admin" or similar).
        event: Event to check.

    Returns:
        True if event should be sent to principal, False to filter out.

    Note:
        Current implementation: if principal is "admin" (authenticated via
        admin token), all events are visible. If RBAC engine is wired in
        future (Task 7.4+), this will check principal.host_id vs event
        payload.host_id for host:read permission.
    """
    # For now, if authenticated (non-None principal), all events visible.
    # In future: check RBAC via `provider.is_authorized(principal, "host:read", ...)`
    return principal is not None
