"""DB-backed hash-chained audit log with periodic Merkle checkpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.crypto.signing import SigningBackend
from server.app.events.bus import Bus
from server.app.events.after_commit import publish_after_commit
from server.app.models.audit import AuditCheckpoint as CheckpointModel
from server.app.models.audit import AuditEntry as AuditEntryModel

from .chain import (
    GENESIS_HASH,
    CheckpointError,
    ChainBrokenError,
    compute_entry_hash,
    merkle_root,
)

# Process-local lock for serializing critical sections of append()
_APPEND_LOCK = asyncio.Lock()


class SqlAuditChain:
    """DB-backed hash-chained audit log with periodic Merkle checkpoints.

    All ops require an AsyncSession; caller controls transactions.
    """

    def __init__(
        self,
        signing_backend: SigningBackend,
        *,
        checkpoint_interval: int = 100,
        event_bus: Bus | None = None,
    ) -> None:
        """Initialize DB-backed audit chain.

        Args:
            signing_backend: Backend for signing checkpoints.
            checkpoint_interval: Create checkpoint every N entries.
            event_bus: Optional event bus for publishing audit events.
        """
        self._backend = signing_backend
        self._checkpoint_interval = checkpoint_interval
        self._event_bus = event_bus

    async def append(
        self,
        session: AsyncSession,
        *,
        actor: str,
        action: str,
        subject: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEntryModel:
        """Append new entry; returns it. Auto-creates checkpoint when (seq+1) % interval == 0.

        The checkpoint covers entries from [last_checkpoint_seq+1 .. current_seq] inclusive.

        Uses asyncio.Lock to serialize critical section: prevents concurrent appends from
        computing the same sequence number (race condition). If IntegrityError occurs due to
        duplicate sequence, retries once.
        """
        if payload is None:
            payload = {}
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Serialize critical section: read-then-insert must not race
        async with _APPEND_LOCK:
            # Get next sequence number by finding max existing sequence
            result = await session.execute(
                select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
            )
            last_entry = result.scalar_one_or_none()
            sequence = 0 if last_entry is None else last_entry.sequence + 1

            # Get prev_hash (last entry's entry_hash or GENESIS_HASH)
            prev_hash = GENESIS_HASH if last_entry is None else last_entry.entry_hash

        # Compute entry_hash (outside lock, not critical)
        entry_hash = compute_entry_hash(
            sequence=sequence,
            timestamp=timestamp,
            actor=actor,
            action=action,
            subject=subject,
            payload=payload,
            prev_hash=prev_hash,
        )

        # Create and insert entry
        entry = AuditEntryModel(
            sequence=sequence,
            timestamp=timestamp,
            actor=actor,
            action=action,
            subject=subject,
            payload=payload,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        try:
            session.add(entry)
            await session.flush()
        except IntegrityError:
            # Duplicate sequence due to race — rollback and retry once
            await session.rollback()
            async with _APPEND_LOCK:
                result = await session.execute(
                    select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
                )
                last_entry = result.scalar_one_or_none()
                sequence = 0 if last_entry is None else last_entry.sequence + 1
                prev_hash = GENESIS_HASH if last_entry is None else last_entry.entry_hash

            entry_hash = compute_entry_hash(
                sequence=sequence,
                timestamp=timestamp,
                actor=actor,
                action=action,
                subject=subject,
                payload=payload,
                prev_hash=prev_hash,
            )

            entry = AuditEntryModel(
                sequence=sequence,
                timestamp=timestamp,
                actor=actor,
                action=action,
                subject=subject,
                payload=payload,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            session.add(entry)
            await session.flush()

        # Auto-checkpoint: if (sequence+1) % interval == 0
        if (sequence + 1) % self._checkpoint_interval == 0:
            await self._checkpoint_now(session, timestamp=datetime.now(timezone.utc))

        # Publish audit event if bus is set (do not include full payload to avoid PII)
        if self._event_bus is not None:
            publish_after_commit(
                session,
                self._event_bus,
                "audit",
                {
                    "sequence": entry.sequence,
                    "actor": entry.actor,
                    "action": entry.action,
                    "subject": entry.subject,
                },
            )

        return entry

    async def length(self, session: AsyncSession) -> int:
        """Return number of entries in chain."""
        result = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
        )
        last_entry = result.scalar_one_or_none()
        return 0 if last_entry is None else last_entry.sequence + 1

    async def head_hash(self, session: AsyncSession) -> bytes:
        """Return last entry_hash, or GENESIS_HASH if empty."""
        result = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
        )
        last_entry = result.scalar_one_or_none()
        return GENESIS_HASH if last_entry is None else last_entry.entry_hash

    async def force_checkpoint(
        self, session: AsyncSession, *, timestamp: datetime | None = None
    ) -> CheckpointModel:
        """Create checkpoint over current head (sequence = length-1).

        Raises CheckpointError if chain empty.
        """
        if await self.length(session) == 0:
            raise CheckpointError("Cannot force checkpoint on empty chain")

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Get the current head
        result = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
        )
        head_entry = result.scalar_one()
        current_sequence = head_entry.sequence

        # Get all entries and compute merkle root
        all_entries = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.asc())
        )
        entries = all_entries.scalars().all()
        leaf_hashes = [e.entry_hash for e in entries]
        root = merkle_root(leaf_hashes)

        # Sign
        signed_message = current_sequence.to_bytes(8, "big") + root
        signature = self._backend.sign(signed_message)

        # Create and insert checkpoint
        checkpoint = CheckpointModel(
            covers_sequence=current_sequence,
            merkle_root=root,
            signature=signature,
            signing_pubkey=self._backend.public_key_bytes(),
            timestamp=timestamp,
        )
        session.add(checkpoint)
        await session.flush()

        return checkpoint

    async def verify(self, session: AsyncSession) -> None:
        """Walk all entries in order; recompute hashes, prev_hash links.

        Walk all checkpoints; recompute merkle_root from covered entries;
        verify signature against backend.trust_anchors().
        Raise ChainBrokenError or CheckpointError on any mismatch.
        """
        # Get all entries in order
        result = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.asc())
        )
        entries = result.scalars().all()

        # Verify chain linkage
        if entries:
            # First entry must have prev_hash == GENESIS_HASH
            if entries[0].prev_hash != GENESIS_HASH:
                raise ChainBrokenError("First entry prev_hash != GENESIS_HASH")

            # Each entry's prev_hash must match predecessor's entry_hash
            for i, entry in enumerate(entries):
                if i > 0:
                    if entry.prev_hash != entries[i - 1].entry_hash:
                        raise ChainBrokenError(
                            f"Entry {i} prev_hash does not match entry {i-1} entry_hash"
                        )

                # Ensure timestamp is timezone-aware for hash computation
                ts = entry.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                # Recompute entry_hash and verify
                recomputed = compute_entry_hash(
                    sequence=entry.sequence,
                    timestamp=ts,
                    actor=entry.actor,
                    action=entry.action,
                    subject=entry.subject,
                    payload=entry.payload,
                    prev_hash=entry.prev_hash,
                )
                if recomputed != entry.entry_hash:
                    raise ChainBrokenError(
                        f"Entry {entry.sequence} entry_hash does not match recomputed hash"
                    )

        # Get all checkpoints in order
        result = await session.execute(
            select(CheckpointModel).order_by(CheckpointModel.covers_sequence.asc())
        )
        checkpoints: list[CheckpointModel] = result.scalars().all()  # type: ignore[assignment]

        # Verify checkpoints
        for checkpoint in checkpoints:
            # Recompute merkle_root from entries up to checkpoint.covers_sequence
            if checkpoint.covers_sequence >= len(entries):
                raise CheckpointError(
                    f"Checkpoint covers_sequence {checkpoint.covers_sequence} exceeds entries"
                )

            entries_for_checkpoint = entries[: checkpoint.covers_sequence + 1]
            leaf_hashes = [e.entry_hash for e in entries_for_checkpoint]
            recomputed_root = merkle_root(leaf_hashes)

            if recomputed_root != checkpoint.merkle_root:
                raise CheckpointError(
                    f"Checkpoint covers_sequence {checkpoint.covers_sequence} "
                    f"merkle_root does not match recomputed root"
                )

            # Verify signature with pinned signing_pubkey
            signed_message = (
                checkpoint.covers_sequence.to_bytes(8, "big") + checkpoint.merkle_root
            )
            if not self._backend.verify_with_pubkey(signed_message, checkpoint.signature, checkpoint.signing_pubkey):
                raise CheckpointError(
                    f"Checkpoint covers_sequence {checkpoint.covers_sequence} "
                    f"signature does not verify with pinned pubkey"
                )

    async def _checkpoint_now(
        self, session: AsyncSession, *, timestamp: datetime | None = None
    ) -> CheckpointModel:
        """Internal helper to create checkpoint at current position.

        Used by append() when interval is reached.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Get the current head
        result = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
        )
        head_entry = result.scalar_one()
        current_sequence = head_entry.sequence

        # Get all entries and compute merkle root
        all_entries = await session.execute(
            select(AuditEntryModel).order_by(AuditEntryModel.sequence.asc())
        )
        entries = all_entries.scalars().all()
        leaf_hashes = [e.entry_hash for e in entries]
        root = merkle_root(leaf_hashes)

        # Sign
        signed_message = current_sequence.to_bytes(8, "big") + root
        signature = self._backend.sign(signed_message)

        # Create and insert checkpoint
        checkpoint = CheckpointModel(
            covers_sequence=current_sequence,
            merkle_root=root,
            signature=signature,
            signing_pubkey=self._backend.public_key_bytes(),
            timestamp=timestamp,
        )
        session.add(checkpoint)
        await session.flush()

        return checkpoint
