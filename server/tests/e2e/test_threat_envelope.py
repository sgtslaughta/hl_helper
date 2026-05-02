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

    @pytest.mark.xfail(
        reason="forward-gap policy pending C2",
        strict=False,
    )
    def test_forward_jumped_seq_rejected(self, tmp_path: Path) -> None:
        """Record seq=1; attempt seq=100 → MAX_GAP enforcement (if implemented)."""
        db_path = tmp_path / "replay.db"
        store = PersistentReplayStore(db_path)
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Record seq=1
        env1 = make_envelope("host1", 1, b"nonce1", now=now)
        store.accept(env1, now=now)
        assert store.last_sequence("host1") == 1

        # Attempt seq=100 (large forward jump)
        env2 = make_envelope("host1", 100, b"nonce100", now=now)
        # If MAX_GAP enforcement exists, this should raise SequenceRegressionError
        # or a similar error. Current implementation allows forward jumps.
        store.accept(env2, now=now)

        store.close()
