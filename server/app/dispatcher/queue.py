"""Durable command queue — DB-backed FIFO per host using Command table.

Provides CommandQueue with async methods for enqueueing, popping (FIFO),
peeking, and expiring overdue commands. Uses the commands table directly
without creating new tables. Idempotent enqueue is backed by a unique
constraint on idempotency_key for cross-process deduplication, with a
bounded process-local LRU cache for fast-path reads within the same process.
"""

from __future__ import annotations

import structlog
from collections import OrderedDict
from datetime import datetime, timezone

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.command import Command, CommandStatus

logger = structlog.get_logger()

_DEFAULT_IDEMPOTENCY_CAPACITY = 4096


class CommandQueue:
    """Durable FIFO command queue per host, backed by Command table.

    Uses (host_id, sequence) ordering to enforce FIFO delivery per host.
    Status transitions: QUEUED -> IN_FLIGHT -> (ACKED/SUCCEEDED/FAILED/etc).
    expire_overdue marks QUEUED rows past expires_at as EXPIRED.

    Idempotent enqueue is DB-backed: a unique constraint on idempotency_key
    ensures cross-process deduplication. A bounded process-local LRU cache
    (size _DEFAULT_IDEMPOTENCY_CAPACITY) provides fast-path reads for repeat
    requests within the same process.
    """

    def __init__(self, *, idempotency_capacity: int = _DEFAULT_IDEMPOTENCY_CAPACITY) -> None:
        self._idempotency_capacity = idempotency_capacity
        # LRU keyed by idempotency_key -> command_id (str). Stores ids only
        # so cached entries never reference detached SQLAlchemy instances
        # across sessions.
        self._idempotency_cache: OrderedDict[str, str] = OrderedDict()

    async def enqueue(
        self,
        session: AsyncSession,
        command: Command,
        *,
        idempotency_key: str | None = None,
    ) -> Command:
        """Persist command to queue; return cached row if idempotency_key matches.

        If `idempotency_key` is supplied:
        1. Check process-local LRU cache first (fast-path for same process).
        2. If not in cache, query DB by unique idempotency_key to handle
           cross-process deduplication. Return existing Command if found.
        3. Else set idempotency_key on the new command and persist.

        The DB unique constraint ensures idempotency is durable across restarts.
        The process-local LRU provides a small read-through cache layer.

        Caller must commit the session for changes to persist.
        """
        # Fast-path: check process-local cache
        if idempotency_key is not None and idempotency_key in self._idempotency_cache:
            cached_id = self._idempotency_cache[idempotency_key]
            self._idempotency_cache.move_to_end(idempotency_key)
            existing = await session.get(Command, cached_id)
            if existing is not None:
                return existing
            # Stale cache entry (row deleted) — fall through to DB check.
            del self._idempotency_cache[idempotency_key]

        # DB-backed check: look up by idempotency_key to handle cross-process dedup
        existing_cmd: Command | None = None
        if idempotency_key is not None:
            result = await session.execute(
                select(Command).where(Command.idempotency_key == idempotency_key)
            )
            existing_cmd = result.scalar_one_or_none()
            if existing_cmd is not None:
                # Update cache and return existing command
                self._idempotency_cache[idempotency_key] = existing_cmd.id
                self._idempotency_cache.move_to_end(idempotency_key)
                while len(self._idempotency_cache) > self._idempotency_capacity:
                    self._idempotency_cache.popitem(last=False)
                return existing_cmd

        # New command: set idempotency_key before adding to session
        if idempotency_key is not None:
            command.idempotency_key = idempotency_key

        # Try to add to session and flush. If a concurrent request inserted
        # the same idempotency_key, IntegrityError is raised on flush.
        # We catch it, rollback, and re-read the existing row.
        session.add(command)
        try:
            await session.flush()
        except IntegrityError as e:
            if idempotency_key is not None and "idempotency_key" in str(e):
                logger.warning(
                    "idempotency_race_caught",
                    idempotency_key=idempotency_key,
                    error=str(e),
                )
                # Rollback to clean the session state
                await session.rollback()
                # Query for the existing row
                logger.debug(
                    "querying_for_existing_row",
                    idempotency_key=idempotency_key,
                )
                result = await session.execute(
                    select(Command).where(Command.idempotency_key == idempotency_key)
                )
                existing_cmd = result.scalar_one_or_none()
                logger.debug(
                    "query_result",
                    found=existing_cmd is not None,
                    idempotency_key=idempotency_key,
                )
                if existing_cmd is not None:
                    # Update cache and return the existing command
                    self._idempotency_cache[idempotency_key] = existing_cmd.id
                    self._idempotency_cache.move_to_end(idempotency_key)
                    while len(self._idempotency_cache) > self._idempotency_capacity:
                        self._idempotency_cache.popitem(last=False)
                    logger.info(
                        "idempotency_race_resolved",
                        idempotency_key=idempotency_key,
                        command_id=existing_cmd.id,
                    )
                    return existing_cmd
                logger.exception(
                    "idempotency_race_row_not_found",
                    idempotency_key=idempotency_key,
                )
                raise
            else:
                # Not an idempotency_key constraint violation — re-raise
                logger.exception(
                    "integrity_error_non_idempotency",
                    idempotency_key=idempotency_key,
                )
                raise

        # Update cache for newly added command
        if idempotency_key is not None:
            self._idempotency_cache[idempotency_key] = command.id
            self._idempotency_cache.move_to_end(idempotency_key)
            while len(self._idempotency_cache) > self._idempotency_capacity:
                self._idempotency_cache.popitem(last=False)

        return command

    def _oldest_queued_stmt(self, host_id: str) -> Select[tuple[Command]]:
        return (
            select(Command)
            .where(Command.host_id == host_id, Command.status == CommandStatus.QUEUED)
            .order_by(Command.sequence.asc())
            .limit(1)
        )

    async def pop(self, session: AsyncSession, host_id: str) -> Command | None:
        """Return oldest QUEUED command for host, transitioning it to IN_FLIGHT.

        Atomicity: uses SELECT ... FOR UPDATE SKIP LOCKED on backends that
        support row locking (Postgres, MySQL); on SQLite, atomicity relies on
        the surrounding transaction (callers should serialize concurrent pops
        on the same host or wrap in BEGIN IMMEDIATE).

        Caller must commit the session.
        """
        stmt = self._oldest_queued_stmt(host_id)
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect in ("postgresql", "mysql"):
            stmt = stmt.with_for_update(skip_locked=True)
        command = (await session.execute(stmt)).scalar_one_or_none()
        if command is None:
            return None
        command.status = CommandStatus.IN_FLIGHT
        return command

    async def peek(self, session: AsyncSession, host_id: str) -> Command | None:
        """Return oldest QUEUED command for host without changing state."""
        result = await session.execute(self._oldest_queued_stmt(host_id))
        row: Command | None = result.scalar_one_or_none()
        return row

    async def expire_overdue(
        self, session: AsyncSession, *, now: datetime | None = None
    ) -> int:
        """Mark QUEUED commands with expires_at < now as EXPIRED.

        Bulk UPDATE in a single statement; returns rows affected.
        Caller must commit.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stmt = (
            update(Command)
            .where(
                Command.status == CommandStatus.QUEUED,
                Command.expires_at < now,
            )
            .values(status=CommandStatus.EXPIRED)
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(stmt)
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)
