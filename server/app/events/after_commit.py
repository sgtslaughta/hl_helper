"""Deferred event publishing until after SQLAlchemy session commit."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from server.app.events.bus import Bus


def publish_after_commit(
    session: AsyncSession,
    bus: Bus,
    channel: str,
    payload: Mapping[str, Any],
) -> None:
    """Schedule a bus.publish to fire when the session's transaction commits.

    If the transaction rolls back, the publish is dropped. Multiple calls
    within a single transaction are batched as a list and published in
    registration order on commit.

    Args:
        session: AsyncSession to attach the after_commit listener to.
        bus: Bus instance to publish events on.
        channel: Channel name for the event.
        payload: Event payload mapping.
    """
    # Use session.info to stash pending publishes and registration flag
    sync_session = session.sync_session
    if "_pending_bus_publishes" not in sync_session.info:
        sync_session.info["_pending_bus_publishes"] = []

    # Add this publish to the pending list (make a copy to avoid mutation issues)
    sync_session.info["_pending_bus_publishes"].append((channel, dict(payload)))

    # Register the flush handler once per session (idempotent via flag)
    if not sync_session.info.get("_after_commit_registered", False):
        sync_session.info["_after_commit_registered"] = True

        # Define the flush handler
        def _flush(session_obj: Any) -> None:
            """Flush all pending publishes via asyncio.create_task."""
            pending = session_obj.info.get("_pending_bus_publishes", [])
            # Schedule each publish as a task (publish is async)
            for ch, pl in pending:
                asyncio.create_task(bus.publish(ch, pl))
            # Clear pending list for next transaction
            session_obj.info["_pending_bus_publishes"] = []

        # Import here to avoid circular dependency at module load time
        from sqlalchemy import event

        # Register the handler on the after_commit event
        event.listen(sync_session, "after_commit", _flush, once=False)
