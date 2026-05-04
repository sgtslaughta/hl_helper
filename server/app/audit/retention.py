"""Audit retention sweeper.

Prunes audit entries older than `audit_retention_days`, preserving Merkle
checkpoints so prior windows remain verifiable. A "prune-checkpoint" is forced
just before deletion so verification can stop at the new chain head.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.models.audit import AuditCheckpoint, AuditEntry

_logger = logging.getLogger(__name__)


class RetentionSweeper:
    """Sweeps audit entries older than the retention window.

    Behavior:
      - retention_days <= 0 → no-op (retain forever)
      - Forces a Merkle checkpoint covering the last surviving entry so the
        retained tail remains chain-verifiable
      - Deletes entries with timestamp < cutoff
      - Preserves all AuditCheckpoint rows (cheap, valuable for verification)
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        chain: SqlAuditChain,
        *,
        retention_days: int,
    ) -> None:
        self._sm = sessionmaker
        self._chain = chain
        self._retention_days = retention_days

    @property
    def retention_days(self) -> int:
        return self._retention_days

    async def sweep(self, *, now: datetime | None = None) -> int:
        """Run one pass. Returns count of deleted entries."""
        if self._retention_days <= 0:
            return 0
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=self._retention_days)

        async with self._sm() as session:
            # Find the highest sequence with timestamp < cutoff (boundary)
            boundary_seq = await session.scalar(
                select(func.max(AuditEntry.sequence)).where(AuditEntry.timestamp < cutoff)
            )
            if boundary_seq is None:
                return 0

            # Force checkpoint covering up to boundary so verification of remaining
            # tail (boundary+1..head) still chains forward correctly.
            try:
                await self._chain.force_checkpoint(session)
                await session.commit()
            except Exception as exc:
                _logger.exception("retention_checkpoint_failed: %s", exc)
                await session.rollback()
                return 0

            # Delete entries below cutoff
            result = await session.execute(
                delete(AuditEntry).where(AuditEntry.timestamp < cutoff)
            )
            await session.commit()
            deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
            _logger.info(
                "audit_retention_swept",
                extra={"deleted": deleted, "cutoff": cutoff.isoformat(), "boundary_seq": boundary_seq},
            )
            return deleted

    async def oldest_entry_age_days(self, *, now: datetime | None = None) -> float | None:
        """Diagnostic: age of oldest surviving entry in days, or None if empty."""
        async with self._sm() as session:
            ts = await session.scalar(select(func.min(AuditEntry.timestamp)))
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ((now or datetime.now(timezone.utc)) - ts).total_seconds() / 86400.0

    async def checkpoint_count(self) -> int:
        async with self._sm() as session:
            n = await session.scalar(select(func.count(AuditCheckpoint.id)))
        return int(n or 0)
