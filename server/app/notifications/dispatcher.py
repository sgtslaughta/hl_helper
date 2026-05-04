"""Notification dispatcher: routes a NotificationMessage to a configured provider.

Backends are async callables: `async (config, message) -> NotificationResult`.
Dispatcher selects backend by provider type, applies retry-with-backoff, and
returns structured result for audit + metric emission by callers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from server.app.models.notification import Notification, NotificationProvider

log = structlog.get_logger(__name__)

Backend = Callable[[dict[str, Any], "NotificationMessage"], Awaitable["NotificationResult"]]


@dataclass(frozen=True)
class NotificationMessage:
    """Provider-agnostic message envelope."""

    title: str
    body: str
    severity: str = "info"  # info|warning|error|critical
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NotificationResult:
    """Outcome of a single send attempt."""

    ok: bool
    provider: str
    detail: str | None = None
    attempts: int = 1


class NotificationDispatcher:
    """Routes messages to configured notification providers.

    Usage:
        d = NotificationDispatcher()
        d.register(NotificationProvider.SMTP, smtp_backend)
        result = await d.send(notification_row, message)
    """

    def __init__(
        self,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._backends: dict[NotificationProvider, Backend] = {}
        self._max_retries = max_retries
        self._backoff = backoff_seconds

    def register(self, provider: NotificationProvider, backend: Backend) -> None:
        self._backends[provider] = backend

    def supports(self, provider: NotificationProvider) -> bool:
        return provider in self._backends

    async def send(
        self,
        notification: Notification,
        message: NotificationMessage,
    ) -> NotificationResult:
        """Dispatch one message via the configured provider.

        Retries with exponential backoff on transient failure (returned ok=False).
        """
        if not notification.enabled:
            return NotificationResult(ok=False, provider=notification.provider.value, detail="disabled")
        backend = self._backends.get(notification.provider)
        if backend is None:
            return NotificationResult(
                ok=False,
                provider=notification.provider.value,
                detail=f"no_backend_registered: {notification.provider.value}",
            )

        attempts = 0
        last_err = "unknown"
        for attempt in range(self._max_retries + 1):
            attempts = attempt + 1
            try:
                result = await backend(notification.config, message)
                if result.ok:
                    return NotificationResult(
                        ok=True,
                        provider=result.provider,
                        detail=result.detail,
                        attempts=attempts,
                    )
                last_err = result.detail or "send_failed"
            except Exception as exc:  # backend bug shouldn't crash caller
                last_err = f"{type(exc).__name__}: {exc}"
                log.warning("notification_backend_exception", provider=notification.provider.value, err=last_err)
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff * (2**attempt))
        return NotificationResult(
            ok=False,
            provider=notification.provider.value,
            detail=last_err,
            attempts=attempts,
        )
