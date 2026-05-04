"""C8 notifications — provider-agnostic dispatcher + SMTP/webhook backends."""

from __future__ import annotations

from server.app.notifications.dispatcher import (
    NotificationDispatcher,
    NotificationMessage,
    NotificationResult,
)

__all__ = [
    "NotificationDispatcher",
    "NotificationMessage",
    "NotificationResult",
]
