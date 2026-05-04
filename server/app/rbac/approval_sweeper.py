"""Approval expiry sweeper.

Marks pending / pending_second approvals as EXPIRED once their expires_at
elapses. Designed to be invoked periodically (e.g., from APScheduler) by
ApprovalSweeper.sweep(). Safe to run concurrently with decide() -- the engine
already handles inline expiry; this batch path catches approvals nobody is
trying to decide.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.models import Approval
from server.app.models.approval import ApprovalState

_logger = logging.getLogger(__name__)


class ApprovalSweeper:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        audit_chain: SqlAuditChain | None = None,
    ) -> None:
        self._sm = sessionmaker
        self._audit = audit_chain

    async def sweep(self, *, now: datetime | None = None) -> int:
        """Run one pass. Returns count of approvals transitioned to EXPIRED."""
        now = now or datetime.now(timezone.utc)
        async with self._sm() as session:
            stmt = select(Approval).where(
                Approval.state.in_(("pending", "pending_second")),
                Approval.expires_at < now,
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                return 0

            ids = [r.id for r in rows]
            await session.execute(
                update(Approval)
                .where(Approval.id.in_(ids))
                .values(state=ApprovalState.EXPIRED, rejected_reason="expired")
            )
            await session.commit()

        if self._audit is not None:
            async with self._sm() as audit_session:
                for aid in ids:
                    try:
                        await self._audit.append(
                            audit_session,
                            actor="system",
                            action="approval.expired",
                            subject=aid,
                            payload={"reason": "ttl_elapsed"},
                        )
                    except Exception as exc:
                        _logger.exception("approval_sweep_audit_failed: %s", exc)
                await audit_session.commit()

        _logger.info("approval_sweep", extra={"expired": len(ids)})
        return len(ids)
