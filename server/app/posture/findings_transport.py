"""C1 transport posture findings."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models import Host
from server.app.posture.model import Finding

log = structlog.get_logger(__name__)


async def hosts_unreachable_recently(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag when any enrolled host has no recent heartbeat (last_seen NULL).

    Heartbeat plumbing is C1; absence is a signal of agent compromise or
    network partition.
    """
    async with sessionmaker() as s:
        unreachable = await s.scalar(
            select(func.count(Host.id)).where(Host.last_seen_at.is_(None))
        )
    if not unreachable:
        return None
    return Finding(
        id="hosts_never_checked_in",
        rule="hosts_never_checked_in",
        severity="medium",
        title="Hosts never checked in",
        summary=f"{unreachable} enrolled host(s) have never reported a heartbeat. "
        "Verify the agent is running, has a valid manifest, and can reach the control plane.",
        docs_url="/docs/transport/heartbeat",
        subject_kind="host",
    )


async def hosts_with_expired_certs(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Flag enrolled hosts whose mTLS cert is past expiry."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    async with sessionmaker() as s:
        expired = await s.scalar(
            select(func.count(Host.id)).where(
                Host.cert_expires_at.is_not(None), Host.cert_expires_at < now
            )
        )
    if not expired:
        return None
    return Finding(
        id="hosts_with_expired_certs",
        rule="hosts_with_expired_certs",
        severity="high",
        title="Hosts with expired mTLS certs",
        summary=f"{expired} host(s) have an expired mTLS certificate. "
        "Trigger reissuance or rotate via the renewal RPC.",
        docs_url="/docs/transport/cert-renewal",
        subject_kind="host",
    )
