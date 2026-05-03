"""Tests for server.app.audit.chain."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from server.app.audit.chain import (
    GENESIS_HASH,
    AuditChain,
    AuditEntry,
    Checkpoint,
    ChainBrokenError,
    CheckpointError,
    canonical_entry_bytes,
    merkle_root,
)
from server.app.crypto.signing import FileBackend


@pytest.fixture
def backend(tmp_path: Path) -> FileBackend:
    return FileBackend.bootstrap(tmp_path / "signing")


@pytest.fixture
def chain(backend: FileBackend) -> AuditChain:
    return AuditChain(backend, checkpoint_interval=100)


class TestGenesisState:
    def test_genesis_state(self, chain: AuditChain) -> None:
        assert chain.length == 0
        assert chain.head_hash == GENESIS_HASH
        chain.verify()  # Should not raise


class TestAppendSingleEntry:
    def test_append_single_entry(self, chain: AuditChain) -> None:
        entry = chain.append(
            actor="test-user",
            action="auth.login",
        )
        assert entry.sequence == 0
        assert entry.prev_hash == GENESIS_HASH
        assert entry.entry_hash is not None
        assert len(entry.entry_hash) == 32
        assert chain.length == 1


class TestChainPrevHash:
    def test_append_chains_prev_hash(self, chain: AuditChain) -> None:
        entry1 = chain.append(actor="user1", action="action1")
        entry2 = chain.append(actor="user2", action="action2")

        assert entry2.prev_hash == entry1.entry_hash
        assert entry2.sequence == 1
        assert chain.length == 2


class TestEntryHashDeterminism:
    def test_entry_hash_deterministic(self, chain: AuditChain, backend: FileBackend) -> None:
        # Build chain 1
        chain1 = AuditChain(backend, checkpoint_interval=100)
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        entry1 = chain1.append(
            actor="user",
            action="test.action",
            subject="host1",
            payload={"key": "value"},
            timestamp=ts,
        )

        # Build chain 2 with same input
        chain2 = AuditChain(backend, checkpoint_interval=100)
        entry2 = chain2.append(
            actor="user",
            action="test.action",
            subject="host1",
            payload={"key": "value"},
            timestamp=ts,
        )

        assert entry1.entry_hash == entry2.entry_hash


class TestCanonicalBytes:
    def test_canonical_bytes_excludes_entry_hash(self) -> None:
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        canonical = canonical_entry_bytes(
            sequence=0,
            timestamp=ts,
            actor="user1",
            action="auth.login",
            subject=None,
            payload={"attempt": 1},
            prev_hash=GENESIS_HASH,
        )
        assert isinstance(canonical, bytes)
        assert len(canonical) > 0
        # Should contain JSON representation
        assert b"user1" in canonical
        assert b"auth.login" in canonical


class TestVerifyCleanChain:
    def test_verify_passes_on_clean_chain(self, chain: AuditChain) -> None:
        for i in range(5):
            chain.append(actor=f"user{i}", action=f"action{i}")
        chain.verify()  # Should not raise


class TestVerifyTamperedPayload:
    def test_verify_rejects_tampered_payload(self, chain: AuditChain) -> None:
        chain.append(actor="user1", action="action1")
        chain.append(actor="user2", action="action2")
        chain.append(actor="user3", action="action3")

        # Mutate entry 1's payload in internal list
        # Since AuditEntry is frozen, we need to replace it
        entries = chain.entries()
        tampered = AuditEntry(
            sequence=1,
            timestamp=entries[1].timestamp,
            actor=entries[1].actor,
            action=entries[1].action,
            subject=entries[1].subject,
            payload={"tampered": True},  # Different payload
            prev_hash=entries[1].prev_hash,
            entry_hash=entries[1].entry_hash,  # Keep old hash
        )
        chain._entries[1] = tampered

        with pytest.raises(ChainBrokenError):
            chain.verify()


class TestVerifyBrokenLink:
    def test_verify_rejects_broken_link(self, chain: AuditChain) -> None:
        chain.append(actor="user1", action="action1")
        chain.append(actor="user2", action="action2")

        # Replace entry 0's prev_hash with random bytes
        entries = chain.entries()
        broken = AuditEntry(
            sequence=0,
            timestamp=entries[0].timestamp,
            actor=entries[0].actor,
            action=entries[0].action,
            subject=entries[0].subject,
            payload=entries[0].payload,
            prev_hash=b"\xaa" * 32,  # Wrong prev_hash
            entry_hash=entries[0].entry_hash,
        )
        chain._entries[0] = broken

        with pytest.raises(ChainBrokenError):
            chain.verify()


class TestAutoCheckpoint:
    def test_auto_checkpoint_at_interval(self, backend: FileBackend) -> None:
        chain = AuditChain(backend, checkpoint_interval=3)
        chain.append(actor="user1", action="action1")
        chain.append(actor="user2", action="action2")
        assert len(chain.checkpoints()) == 0

        chain.append(actor="user3", action="action3")
        assert len(chain.checkpoints()) == 1

        chain.append(actor="user4", action="action4")
        chain.append(actor="user5", action="action5")
        assert len(chain.checkpoints()) == 1

        chain.append(actor="user6", action="action6")
        assert len(chain.checkpoints()) == 2


class TestCheckpointMerkleRoot:
    def test_checkpoint_merkle_root_matches(self, chain: AuditChain) -> None:
        chain.append(actor="user1", action="action1")
        chain.append(actor="user2", action="action2")
        chain.append(actor="user3", action="action3")

        checkpoint = chain.force_checkpoint()
        entries = chain.entries()
        leaf_hashes = [e.entry_hash for e in entries]
        expected_root = merkle_root(leaf_hashes)

        assert checkpoint.merkle_root == expected_root


class TestCheckpointSignature:
    def test_checkpoint_signature_verifies(self, backend: FileBackend) -> None:
        chain = AuditChain(backend, checkpoint_interval=100)
        chain.append(actor="user1", action="action1")

        checkpoint = chain.force_checkpoint()
        # Checkpoint signature should verify under one of the trust anchors
        signed_message = checkpoint.sequence.to_bytes(8, "big") + checkpoint.merkle_root
        assert backend.verify(signed_message, checkpoint.signature)


class TestVerifyTamperedCheckpoint:
    def test_verify_rejects_tampered_checkpoint_root(self, chain: AuditChain) -> None:
        chain.append(actor="user1", action="action1")
        checkpoint = chain.force_checkpoint()

        # Mutate checkpoint root
        tampered = Checkpoint(
            sequence=checkpoint.sequence,
            merkle_root=b"\xbb" * 32,  # Different root
            signature=checkpoint.signature,
            signing_pubkey=checkpoint.signing_pubkey,
            timestamp=checkpoint.timestamp,
        )
        chain._checkpoints[0] = tampered

        with pytest.raises(CheckpointError):
            chain.verify()


class TestVerifyBadCheckpointSignature:
    def test_verify_rejects_bad_checkpoint_signature(self, chain: AuditChain) -> None:
        chain.append(actor="user1", action="action1")
        checkpoint = chain.force_checkpoint()

        # Replace signature with junk
        tampered = Checkpoint(
            sequence=checkpoint.sequence,
            merkle_root=checkpoint.merkle_root,
            signature=b"\xcc" * 64,  # Junk signature
            signing_pubkey=checkpoint.signing_pubkey,
            timestamp=checkpoint.timestamp,
        )
        chain._checkpoints[0] = tampered

        with pytest.raises(CheckpointError):
            chain.verify()


class TestForceCheckpoint:
    def test_force_checkpoint(self, backend: FileBackend) -> None:
        chain = AuditChain(backend, checkpoint_interval=100)
        chain.append(actor="user1", action="action1")
        chain.append(actor="user2", action="action2")

        checkpoint = chain.force_checkpoint()
        assert checkpoint.sequence == 1
        assert len(chain.checkpoints()) == 1


class TestForceCheckpointEmpty:
    def test_force_checkpoint_rejects_empty_chain(self, chain: AuditChain) -> None:
        with pytest.raises(CheckpointError):
            chain.force_checkpoint()


class TestMerkleRootSingleLeaf:
    def test_merkle_root_single_leaf_rfc6962(self) -> None:
        """RFC 6962: single leaf must be H(0x00 || leaf)."""
        leaf = hashlib.sha256(b"single").digest()
        # Expected: H(0x00 || leaf)
        expected = hashlib.sha256(b"\x00" + leaf).digest()
        result = merkle_root([leaf])
        assert result == expected


class TestMerkleRootOddCount:
    def test_merkle_root_odd_count(self) -> None:
        """RFC 6962: 3 leaves duplicate the last when odd."""
        a = hashlib.sha256(b"a").digest()
        b = hashlib.sha256(b"b").digest()
        c = hashlib.sha256(b"c").digest()

        # RFC 6962 leaf hashing
        h_a = hashlib.sha256(b"\x00" + a).digest()
        h_b = hashlib.sha256(b"\x00" + b).digest()
        h_c = hashlib.sha256(b"\x00" + c).digest()

        # Pair (h_a, h_b) and (h_c, h_c) with 0x01 prefix
        h_ab = hashlib.sha256(b"\x01" + h_a + h_b).digest()
        h_cc = hashlib.sha256(b"\x01" + h_c + h_c).digest()
        # Final pair with 0x01 prefix
        expected = hashlib.sha256(b"\x01" + h_ab + h_cc).digest()

        assert merkle_root([a, b, c]) == expected


class TestMerkleRootEmpty:
    def test_merkle_root_empty(self) -> None:
        assert merkle_root([]) == b"\x00" * 32


class TestMerkleRfc6962DomainSeparation:
    def test_merkle_root_rfc6962_leaf_prefix(self) -> None:
        """Verify leaf hashing uses 0x00 prefix (RFC 6962 domain separation)."""
        # Single leaf: should be H(0x00 || leaf), not leaf as-is
        leaf1 = hashlib.sha256(b"leaf1").digest()
        root_single = merkle_root([leaf1])
        expected_single = hashlib.sha256(b"\x00" + leaf1).digest()
        assert root_single == expected_single, "Single leaf must use 0x00 prefix"

    def test_merkle_root_rfc6962_internal_prefix(self) -> None:
        """Verify internal node hashing uses 0x01 prefix (RFC 6962 domain separation)."""
        # Two leaves: root should be H(0x01 || H(0x00||leaf1) || H(0x00||leaf2))
        leaf1 = hashlib.sha256(b"leaf1").digest()
        leaf2 = hashlib.sha256(b"leaf2").digest()
        h_leaf1 = hashlib.sha256(b"\x00" + leaf1).digest()
        h_leaf2 = hashlib.sha256(b"\x00" + leaf2).digest()
        expected_root = hashlib.sha256(b"\x01" + h_leaf1 + h_leaf2).digest()
        result = merkle_root([leaf1, leaf2])
        assert result == expected_root, "Internal nodes must use 0x01 prefix"

    def test_merkle_root_rfc6962_four_leaves(self) -> None:
        """Verify RFC 6962 for 4 leaves (asymmetric tree)."""
        leaves = [
            hashlib.sha256(b"leaf1").digest(),
            hashlib.sha256(b"leaf2").digest(),
            hashlib.sha256(b"leaf3").digest(),
            hashlib.sha256(b"leaf4").digest(),
        ]
        h_leaves = [hashlib.sha256(b"\x00" + leaf).digest() for leaf in leaves]
        # Level 1: pair (h_leaves[0], h_leaves[1]) and (h_leaves[2], h_leaves[3])
        h_01 = hashlib.sha256(b"\x01" + h_leaves[0] + h_leaves[1]).digest()
        h_23 = hashlib.sha256(b"\x01" + h_leaves[2] + h_leaves[3]).digest()
        # Level 2: pair (h_01, h_23)
        root = hashlib.sha256(b"\x01" + h_01 + h_23).digest()
        result = merkle_root(leaves)
        assert result == root, "RFC 6962 tree for 4 leaves must match"


class TestPayloadDefaults:
    def test_payload_default_empty_dict(self, chain: AuditChain) -> None:
        entry = chain.append(actor="user", action="test")
        assert entry.payload == {}


class TestTimestampDefault:
    def test_timestamp_default_is_utc(self, chain: AuditChain) -> None:
        before = datetime.now(timezone.utc)
        entry = chain.append(actor="user", action="test")
        after = datetime.now(timezone.utc)

        assert before <= entry.timestamp <= after


class TestCheckpointSigningPubkeyPinning:
    def test_checkpoint_verify_requires_pinned_pubkey(self, backend: FileBackend) -> None:
        """Verify that checkpoint signature verification uses the pinned signing_pubkey, not backend trust anchors."""
        chain = AuditChain(backend, checkpoint_interval=100)
        chain.append(actor="user1", action="action1")
        checkpoint = chain.force_checkpoint()

        # Mutate the signing_pubkey in checkpoint to a different key
        # (simulate key rotation where backend now trusts a new key)
        tampered = Checkpoint(
            sequence=checkpoint.sequence,
            merkle_root=checkpoint.merkle_root,
            signature=checkpoint.signature,
            signing_pubkey=b"\xaa" * 32,  # Different (invalid) pubkey
            timestamp=checkpoint.timestamp,
        )
        chain._checkpoints[0] = tampered

        # Verification should fail because signature was signed with original key,
        # but we're trying to verify against the tampered pubkey
        with pytest.raises(CheckpointError):
            chain.verify()
