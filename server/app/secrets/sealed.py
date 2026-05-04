"""Sealed-mode monitor for secrets broker.

Polls the configured Vault backend's ``health_check`` and transitions the
broker into a ``degraded_read_only`` mode when the backend reports sealed
for at least ``grace_seconds`` (default 5 minutes). In degraded mode:

* Cached reads continue to be served from ``BrokerCache`` until their TTL.
* Lookups for non-cached refs raise
  :class:`server.app.secrets.backends.base.BackendSealed`.

Recovery: once the backend reports unsealed for at least
``recovery_seconds`` (default 30s), the monitor exits degraded mode.

Bus events are published on the dedicated ``secrets.status`` channel:

* ``{"type": "secrets.sealed_degraded", "since": <iso8601>}`` on enter.
* ``{"type": "secrets.recovered", "at": <iso8601>}`` on exit.

The dedicated channel keeps host-status concerns separate so UI banner
subscribers can listen to a single, focused topic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from server.app.events.bus import Bus

log = structlog.get_logger(__name__)


DEFAULT_POLL_INTERVAL_S = 30.0
DEFAULT_GRACE_SECONDS = 300  # 5 minutes
DEFAULT_RECOVERY_SECONDS = 30
SEALED_STATUS_CHANNEL = "secrets.status"


@dataclass
class SealedState:
    """Snapshot of monitor state."""

    active: bool
    since: datetime | None
    last_health: dict[str, Any] | None = field(default=None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SealedModeMonitor:
    """Polls Vault health and toggles broker degraded read-only state.

    Args:
        broker: The :class:`SecretsBroker` to flag (mon attaches itself
            via ``broker.sealed_monitor``).
        bus: Optional event :class:`Bus` for status announcements.
        vault_backend: Backend exposing async ``health_check()`` returning
            ``{"sealed": bool, ...}``.
        poll_interval_seconds: Sleep between polls in the background task.
        grace_seconds: Seconds backend must be continuously sealed before
            entering degraded mode.
        recovery_seconds: Seconds backend must be continuously unsealed
            before exiting degraded mode.
    """

    def __init__(
        self,
        broker: Any,
        bus: Bus | None,
        vault_backend: Any,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_S,
        grace_seconds: int = DEFAULT_GRACE_SECONDS,
        recovery_seconds: int = DEFAULT_RECOVERY_SECONDS,
    ) -> None:
        self.broker = broker
        self.bus = bus
        self.vault_backend = vault_backend
        self.poll_interval = poll_interval_seconds
        self.grace_seconds = grace_seconds
        self.recovery_seconds = recovery_seconds

        self._state = SealedState(active=False, since=None, last_health=None)
        # Continuous-condition timestamps for entering/exiting.
        self._sealed_since: datetime | None = None
        self._unsealed_since: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

        # Auto-attach so broker can consult is_degraded() without explicit wiring.
        try:
            setattr(broker, "sealed_monitor", self)
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def is_degraded(self) -> bool:
        return self._state.active

    def last_status(self) -> SealedState:
        return self._state

    async def start(self) -> None:
        """Launch the background polling task."""
        if self._task is not None and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name="sealed-monitor")

    async def stop(self) -> None:
        """Cancel the polling task (idempotent)."""
        self._stopped.set()
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _run(self) -> None:
        """Background loop calling ``_poll_once`` on an interval."""
        while not self._stopped.is_set():
            try:
                await self._poll_once()
            except Exception as e:  # pragma: no cover - defensive
                log.warning("sealed_monitor_poll_failed", exc=str(e))
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue

    async def _poll_once(self) -> None:
        """Single health probe + state-machine tick. Exposed for tests."""
        try:
            health = await self.vault_backend.health_check()
        except Exception as e:
            log.warning("sealed_monitor_health_check_error", exc=str(e))
            # Treat unknown as sealed (fail-closed) for purposes of grace timer
            health = {"sealed": True, "_error": str(e)}

        sealed = bool(health.get("sealed", False))
        now = _now()
        self._state = SealedState(
            active=self._state.active,
            since=self._state.since,
            last_health=dict(health),
        )

        if sealed:
            # Track first observation of a continuous sealed window.
            if self._sealed_since is None:
                self._sealed_since = now
            self._unsealed_since = None

            if not self._state.active:
                elapsed = (now - self._sealed_since).total_seconds()
                if elapsed >= self.grace_seconds:
                    await self._enter_degraded(now)
        else:
            # Track first observation of a continuous unsealed window.
            if self._unsealed_since is None:
                self._unsealed_since = now
            self._sealed_since = None

            if self._state.active:
                elapsed = (now - self._unsealed_since).total_seconds()
                if elapsed >= self.recovery_seconds:
                    await self._exit_degraded(now)

    async def _enter_degraded(self, now: datetime) -> None:
        self._state = SealedState(
            active=True, since=now, last_health=self._state.last_health
        )
        log.warning("secrets_sealed_degraded_entered", since=now.isoformat())
        if self.bus is not None:
            try:
                await self.bus.publish(
                    SEALED_STATUS_CHANNEL,
                    {"type": "secrets.sealed_degraded", "since": now.isoformat()},
                )
            except Exception as e:  # pragma: no cover - defensive
                log.warning("sealed_event_publish_failed", exc=str(e))

    async def _exit_degraded(self, now: datetime) -> None:
        self._state = SealedState(
            active=False, since=None, last_health=self._state.last_health
        )
        log.info("secrets_sealed_degraded_recovered", at=now.isoformat())
        if self.bus is not None:
            try:
                await self.bus.publish(
                    SEALED_STATUS_CHANNEL,
                    {"type": "secrets.recovered", "at": now.isoformat()},
                )
            except Exception as e:  # pragma: no cover - defensive
                log.warning("sealed_event_publish_failed", exc=str(e))
