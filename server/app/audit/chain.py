"""Append-only hash-chained audit log with periodic Merkle checkpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from server.app.crypto.signing import SigningBackend

GENESIS_HASH = b"\x00" * 32


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit log entry with hash chain."""

    sequence: int  # 0-indexed monotonic
    timestamp: datetime  # UTC
    actor: str  # user id / "system" / agent host id
    action: str  # "host.enroll", "command.dispatch", "auth.login", etc.
    subject: str | None  # target id (host id, user id, plugin id, ...)
    payload: dict[str, Any]  # action-specific structured data
    prev_hash: bytes  # 32 bytes
    entry_hash: bytes  # 32 bytes — sha256 over canonical(self minus entry_hash)


@dataclass(frozen=True)
class Checkpoint:
    """Merkle checkpoint over a range of entries."""

    sequence: int  # last entry sequence covered (inclusive)
    merkle_root: bytes  # 32 bytes
    signature: bytes  # signing backend signature over (sequence || merkle_root)
    signing_pubkey: bytes  # raw 32-byte Ed25519 pubkey used at sign time
    timestamp: datetime


class AuditChainError(Exception):
    """Base audit chain exception."""


class ChainBrokenError(AuditChainError):
    """Entry hash or link validation failed."""


class CheckpointError(AuditChainError):
    """Checkpoint validation failed."""


def canonical_entry_bytes(
    sequence: int,
    timestamp: datetime,
    actor: str,
    action: str,
    subject: str | None,
    payload: dict[str, Any],
    prev_hash: bytes,
) -> bytes:
    """Deterministic bytes used for entry_hash computation.

    JSON with sort_keys=True, separators=(',',':').
    prev_hash hex-encoded.
    timestamp ISO 8601 with 'Z' suffix.
    """
    data = {
        "sequence": sequence,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "actor": actor,
        "action": action,
        "subject": subject,
        "payload": payload,
        "prev_hash": prev_hash.hex(),
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_entry_hash(
    sequence: int,
    timestamp: datetime,
    actor: str,
    action: str,
    subject: str | None,
    payload: dict[str, Any],
    prev_hash: bytes,
) -> bytes:
    """sha256(canonical_entry_bytes(...))."""
    return hashlib.sha256(
        canonical_entry_bytes(
            sequence=sequence,
            timestamp=timestamp,
            actor=actor,
            action=action,
            subject=subject,
            payload=payload,
            prev_hash=prev_hash,
        )
    ).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    """RFC 6962 binary Merkle tree with domain separation.

    Leaf nodes: H(0x00 || leaf_data)
    Internal nodes: H(0x01 || left || right)
    Odd leaf at level: duplicate the last leaf
    Empty input → 32 zero bytes.

    Args:
        leaves: Pre-hashed leaf values (e.g., entry_hash from audit entries).

    Returns:
        Root hash with RFC 6962 domain separation applied.
    """
    if not leaves:
        return GENESIS_HASH

    # RFC 6962: hash leaves with 0x00 prefix
    leaf_level = [hashlib.sha256(b"\x00" + leaf).digest() for leaf in leaves]

    # Build tree level by level with 0x01 prefix for internal nodes
    current_level = leaf_level

    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            if i + 1 < len(current_level):
                left = current_level[i]
                right = current_level[i + 1]
            else:
                # Odd count: duplicate last node
                left = current_level[i]
                right = current_level[i]
            # RFC 6962: internal nodes use 0x01 prefix
            parent = hashlib.sha256(b"\x01" + left + right).digest()
            next_level.append(parent)
        current_level = next_level

    return current_level[0]


class AuditChain:
    """In-memory append-only chain with Merkle checkpoints."""

    def __init__(
        self, signing_backend: SigningBackend, *, checkpoint_interval: int = 100
    ) -> None:
        """Initialize audit chain.

        Args:
            signing_backend: Backend for signing checkpoints.
            checkpoint_interval: Create checkpoint every N entries (after entry
                at sequence N-1, i.e., when count reaches N).
        """
        self._backend = signing_backend
        self._checkpoint_interval = checkpoint_interval
        self._entries: list[AuditEntry] = []
        self._checkpoints: list[Checkpoint] = []

    @property
    def length(self) -> int:
        """Number of entries in chain."""
        return len(self._entries)

    @property
    def head_hash(self) -> bytes:
        """Last entry_hash, or GENESIS_HASH if empty."""
        if not self._entries:
            return GENESIS_HASH
        return self._entries[-1].entry_hash

    def append(
        self,
        *,
        actor: str,
        action: str,
        subject: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEntry:
        """Append new entry; returns it. Auto-creates checkpoint when length % interval == 0.

        The checkpoint covers entries from [last_checkpoint_seq+1 .. current_seq] inclusive.
        """
        if payload is None:
            payload = {}
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        sequence = len(self._entries)
        prev_hash = self.head_hash

        entry_hash = compute_entry_hash(
            sequence=sequence,
            timestamp=timestamp,
            actor=actor,
            action=action,
            subject=subject,
            payload=payload,
            prev_hash=prev_hash,
        )

        entry = AuditEntry(
            sequence=sequence,
            timestamp=timestamp,
            actor=actor,
            action=action,
            subject=subject,
            payload=payload,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )

        self._entries.append(entry)

        # Auto-checkpoint: after appending, if new length is divisible by interval
        if len(self._entries) % self._checkpoint_interval == 0:
            # Create checkpoint covering entries up to current sequence
            current_sequence = len(self._entries) - 1
            leaf_hashes = [e.entry_hash for e in self._entries]
            root = merkle_root(leaf_hashes)

            signed_message = current_sequence.to_bytes(8, "big") + root
            signature = self._backend.sign(signed_message)

            checkpoint = Checkpoint(
                sequence=current_sequence,
                merkle_root=root,
                signature=signature,
                signing_pubkey=self._backend.public_key_bytes(),
                timestamp=datetime.now(timezone.utc),
            )
            self._checkpoints.append(checkpoint)

        return entry

    def entries(self) -> list[AuditEntry]:
        """Return list of all entries."""
        return self._entries[:]

    def checkpoints(self) -> list[Checkpoint]:
        """Return list of all checkpoints."""
        return self._checkpoints[:]

    def verify(self) -> None:
        """Walk chain: every entry's prev_hash matches predecessor's entry_hash; entry_hash matches recompute.
        Each checkpoint's merkle_root recomputes; signature verifies under one of backend.trust_anchors().
        Raises ChainBrokenError or CheckpointError on any mismatch.
        """
        # Verify chain linkage
        if self._entries:
            # First entry must have prev_hash == GENESIS_HASH
            if self._entries[0].prev_hash != GENESIS_HASH:
                raise ChainBrokenError("First entry prev_hash != GENESIS_HASH")

            # Each entry's prev_hash must match predecessor's entry_hash
            for i, entry in enumerate(self._entries):
                if i > 0:
                    if entry.prev_hash != self._entries[i - 1].entry_hash:
                        raise ChainBrokenError(
                            f"Entry {i} prev_hash does not match entry {i-1} entry_hash"
                        )

                # Recompute entry_hash and verify
                recomputed = compute_entry_hash(
                    sequence=entry.sequence,
                    timestamp=entry.timestamp,
                    actor=entry.actor,
                    action=entry.action,
                    subject=entry.subject,
                    payload=entry.payload,
                    prev_hash=entry.prev_hash,
                )
                if recomputed != entry.entry_hash:
                    raise ChainBrokenError(
                        f"Entry {i} entry_hash does not match recomputed hash"
                    )

        # Verify checkpoints
        for i, checkpoint in enumerate(self._checkpoints):
            # Recompute merkle_root from entries up to checkpoint.sequence
            if checkpoint.sequence >= len(self._entries):
                raise CheckpointError(
                    f"Checkpoint {i} sequence {checkpoint.sequence} exceeds entries"
                )

            entries_for_checkpoint = self._entries[: checkpoint.sequence + 1]
            leaf_hashes = [e.entry_hash for e in entries_for_checkpoint]
            recomputed_root = merkle_root(leaf_hashes)

            if recomputed_root != checkpoint.merkle_root:
                raise CheckpointError(
                    f"Checkpoint {i} merkle_root does not match recomputed root"
                )

            # Verify signature with the exact signing_pubkey stored in checkpoint
            # (not the backend's current trust anchors, to enforce key pinning)
            signed_message = checkpoint.sequence.to_bytes(8, "big") + checkpoint.merkle_root
            if not self._backend.verify_with_pubkey(signed_message, checkpoint.signature, checkpoint.signing_pubkey):
                raise CheckpointError(f"Checkpoint {i} signature does not verify with pinned pubkey")

    def force_checkpoint(self, *, timestamp: datetime | None = None) -> Checkpoint:
        """Create checkpoint over current head (sequence = length-1).
        Raises CheckpointError if chain empty.
        """
        if not self._entries:
            raise CheckpointError("Cannot force checkpoint on empty chain")

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        current_sequence = len(self._entries) - 1
        leaf_hashes = [e.entry_hash for e in self._entries]
        root = merkle_root(leaf_hashes)

        signed_message = current_sequence.to_bytes(8, "big") + root
        signature = self._backend.sign(signed_message)

        checkpoint = Checkpoint(
            sequence=current_sequence,
            merkle_root=root,
            signature=signature,
            signing_pubkey=self._backend.public_key_bytes(),
            timestamp=timestamp,
        )
        self._checkpoints.append(checkpoint)
        return checkpoint
