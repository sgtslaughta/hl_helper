"""Phase 8 threat-model E2E tests for envelope signing and replay protection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from server.app.crypto import envelope
from server.app.crypto.envelope import DuplicateNonceError
from server.app.crypto.replay_store import PersistentReplayStore
from server.app.crypto.signing import FileBackend
from server.app.grpc._pb import fleet  # noqa: F401  triggers sys.path injection
from server.tests.e2e.conftest import make_envelope


class TestTamperingAndSignatures:
    """Threat model: command tampering detection."""

    def test_tampered_command_rejected(self, tmp_path: Path) -> None:
        """Sign envelope with key A, mutate command_id, verify with key A → False."""
        backend = FileBackend.bootstrap(tmp_path / "signing")
        env = make_envelope("host1", 1, b"nonce1")

        # Sign the envelope
        envelope.sign_command(env, backend)
        original_sig = env.signature

        # Tamper: mutate one byte of command_id
        env.command_id = "cmd-host1-999"

        # Verify should fail
        assert envelope.verify_command(env, backend.trust_anchors()) is False

        # Original signature must be preserved (we only mutated command_id)
        assert env.signature == original_sig


class TestReplayProtection:
    """Threat model: command replay detection."""

    def test_replayed_command_rejected(self, tmp_path: Path) -> None:
        """Record (host, seq, nonce); attempt same nonce again → DuplicateNonceError."""
        db_path = tmp_path / "replay.db"
        store = PersistentReplayStore(db_path)
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # First submission
        env1 = make_envelope("host1", 1, b"nonce_replay", now=now)
        store.accept(env1, now=now)

        # Attempt replay with same nonce (different sequence number)
        env2 = make_envelope("host1", 2, b"nonce_replay", now=now)
        with pytest.raises(DuplicateNonceError):
            store.accept(env2, now=now)

        store.close()


class TestSequenceGapPolicy:
    """Threat model: forward sequence jump detection (phase 8 policy)."""

    def test_forward_jumped_seq_rejected_when_policy_enabled(self, tmp_path: Path) -> None:
        """seq=1 -> seq=100 with max_forward_gap=10 raises SequenceRegressionError."""
        from server.app.crypto.replay_store import SequenceRegressionError

        db_path = tmp_path / "replay.db"
        store = PersistentReplayStore(db_path, max_forward_gap=10)
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        env1 = make_envelope("host1", 1, b"nonce1", now=now)
        store.accept(env1, now=now)
        assert store.last_sequence("host1") == 1

        env2 = make_envelope("host1", 100, b"nonce100", now=now)
        with pytest.raises(SequenceRegressionError):
            store.accept(env2, now=now)

        store.close()

    def test_forward_gap_within_limit_accepted(self, tmp_path: Path) -> None:
        """Gap within max_forward_gap should be allowed (agent restart scenario)."""
        db_path = tmp_path / "replay.db"
        store = PersistentReplayStore(db_path, max_forward_gap=10)
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store.accept(make_envelope("host1", 1, b"n1", now=now), now=now)
        store.accept(make_envelope("host1", 5, b"n5", now=now), now=now)
        assert store.last_sequence("host1") == 5

        store.close()

    def test_forward_gap_disabled_by_default(self, tmp_path: Path) -> None:
        """Default (max_forward_gap=0) preserves permissive behavior."""
        db_path = tmp_path / "replay.db"
        store = PersistentReplayStore(db_path)
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store.accept(make_envelope("host1", 1, b"n1", now=now), now=now)
        store.accept(make_envelope("host1", 1000000, b"n2", now=now), now=now)
        assert store.last_sequence("host1") == 1000000

        store.close()
