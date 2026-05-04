"""C2 RBAC + control-plane posture findings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models import Approval, Binding, Role, User
from server.app.models.binding import PrincipalType
from server.app.posture.model import Finding

log = structlog.get_logger(__name__)

_ADMIN_ROLE_NAMES = ("owner", "admin")


async def no_owner_account(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Critical: a fleet without any owner account is unrecoverable on lockout."""
    async with sessionmaker() as s:
        owner_count = await s.scalar(
            select(func.count(User.id))
            .join(Binding, Binding.principal_id == User.id)
            .join(Role, Role.id == Binding.role_id)
            .where(
                Binding.principal_type == PrincipalType.USER,
                Role.name == "owner",
            )
        )
    if owner_count and owner_count > 0:
        return None
    return Finding(
        id="no_owner_account",
        rule="no_owner_account",
        severity="critical",
        title="No owner account configured",
        summary="No user is bound to the owner role. The fleet has no break-glass account.",
        docs_url="/docs/rbac/owner-role",
        subject_kind="global",
    )


async def stale_pending_approvals(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Pending approvals older than their expiry but never expired -> sweeper not running."""
    now = datetime.now(timezone.utc)
    async with sessionmaker() as s:
        stale = await s.scalar(
            select(func.count(Approval.id)).where(
                Approval.state.in_(("pending", "pending_second")),
                Approval.expires_at < now - timedelta(minutes=5),
            )
        )
    if not stale:
        return None
    return Finding(
        id="stale_pending_approvals",
        rule="stale_pending_approvals",
        severity="medium",
        title="Stale pending approvals",
        summary=f"{stale} approval(s) past expiry remain in pending state. "
        "Verify the approval cleanup job is running.",
        docs_url="/docs/control-plane/approvals",
        subject_kind="global",
    )


async def excessive_admin_count(
    sessionmaker: async_sessionmaker[AsyncSession], **_: Any
) -> Finding | None:
    """Info: more than 10 users hold admin/owner role -- review least-privilege."""
    async with sessionmaker() as s:
        admins = await s.scalar(
            select(func.count(func.distinct(User.id)))
            .join(Binding, Binding.principal_id == User.id)
            .join(Role, Role.id == Binding.role_id)
            .where(
                Binding.principal_type == PrincipalType.USER,
                Role.name.in_(_ADMIN_ROLE_NAMES),
            )
        )
    if not admins or admins <= 10:
        return None
    return Finding(
        id="excessive_admin_count",
        rule="excessive_admin_count",
        severity="info",
        title="Many admin/owner accounts",
        summary=f"{admins} users hold admin or owner role. "
        "Audit for least-privilege; consider scoped roles instead.",
        docs_url="/docs/rbac/least-privilege",
        subject_kind="global",
    )
