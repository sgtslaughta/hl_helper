"""Tests for server.app.crypto.envelope: signing, verification, and replay protection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from server.app.crypto import envelope
from server.app.crypto.signing import FileBackend
from server.app.grpc._pb import fleet  # noqa: F401  triggers sys.path injection
from server.app.grpc._pb.fleet.v1 import envelope_pb2


def _make_envelope(
    host_id: str,
    sequence: int,
    nonce: bytes,
    ttl_seconds: int = 3600,
    now: datetime | None = None,
) -> envelope_pb2.CommandEnvelope:
    """Factory to build a CommandEnvelope with PkgUpdate payload."""
    if now is None:
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)

    env = envelope_pb2.CommandEnvelope()
    env.command_id = f"cmd-{host_id}-{sequence}"
    env.host_id = host_id
    env.sequence = sequence
    env.nonce = nonce
    env.issued_at.FromDatetime(now)
    env.expires_at.FromDatetime(expires)
    env.issued_by = "test-server"

    # Set PkgUpdate payload
    env.pkg_update.classes.append("base")
    env.pkg_update.dry_run = False

    return env


class TestCanonicalBytes:
    """Tests for canonical_bytes function."""

    def test_canonical_bytes_excludes_signature(self) -> None:
        """canonical_bytes should match when signature field is cleared."""
        env = _make_envelope("host1", 1, b"nonce1")
        env.signature = b"junk-signature"

        canonical_with_junk = envelope.canonical_bytes(env)

        env.signature = b""
        canonical_empty = envelope.canonical_bytes(env)

        assert canonical_with_junk == canonical_empty

    def test_canonical_bytes_deterministic(self) -> None:
        """Two identical envelopes should produce identical canonical bytes."""
        env1 = _make_envelope("host1", 1, b"nonce1")
        env2 = _make_envelope("host1", 1, b"nonce1")

        assert envelope.canonical_bytes(env1) == envelope.canonical_bytes(env2)


class TestSignCommand:
    """Tests for sign_command function."""

    def test_sign_command_sets_signature_in_place(self, tmp_path: Path) -> None:
        """sign_command should set env.signature and return same env."""
        backend = FileBackend.bootstrap(tmp_path / "signing")
        env = _make_envelope("host1", 1, b"nonce1")

        result = envelope.sign_command(env, backend)

        assert result is env  # Same object
        assert env.signature != b""
        assert len(env.signature) > 0


class TestVerifyCommand:
    """Tests for verify_command function."""

    def test_verify_rejects_tampered_payload(self, tmp_path: Path) -> None:
        """Verify should reject an envelope where payload was mutated after signing."""
        backend = FileBackend.bootstrap(tmp_path / "signing")
        env = _make_envelope("host1", 1, b"nonce1")
        envelope.sign_command(env, backend)

        # Tamper with payload
        env.pkg_update.classes.append("extra-class")

        assert envelope.verify_command(env, backend.trust_anchors()) is False

    def test_verify_rejects_wrong_anchor(self, tmp_path: Path) -> None:
        """Verify should reject if signed by a different backend."""
        backend_a = FileBackend.bootstrap(tmp_path / "a")
        backend_b = FileBackend.bootstrap(tmp_path / "b")

        env = _make_envelope("host1", 1, b"nonce1")
        envelope.sign_command(env, backend_a)

        # Verify with wrong backend's anchors
        assert envelope.verify_command(env, backend_b.trust_anchors()) is False

    def test_sign_then_verify_roundtrip(self, tmp_path: Path) -> None:
        """Sign an envelope and verify it succeeds with correct trust anchors."""
        backend = FileBackend.bootstrap(tmp_path / "signing")
        env = _make_envelope("host1", 1, b"nonce1")

        envelope.sign_command(env, backend)

        assert envelope.verify_command(env, backend.trust_anchors()) is True


class TestSequenceTracker:
    """Tests for SequenceTracker class."""

    def test_sequence_tracker_accepts_increasing(self) -> None:
        """Accepting sequences 1, 2, 3 for same host should succeed."""
        tracker = envelope.SequenceTracker()
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for seq in [1, 2, 3]:
            env = _make_envelope("host1", seq, f"nonce{seq}".encode(), now=now)
            tracker.accept(env, now=now)  # Should not raise

    def test_sequence_tracker_rejects_replay_same_seq(self) -> None:
        """Sequence 5 then sequence 5 should raise SequenceRegressionError."""
        tracker = envelope.SequenceTracker()
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        env1 = _make_envelope("host1", 5, b"nonce1", now=now)
        tracker.accept(env1, now=now)

        env2 = _make_envelope("host1", 5, b"nonce2", now=now)
        with pytest.raises(envelope.SequenceRegressionError):
            tracker.accept(env2, now=now)

    def test_sequence_tracker_rejects_backwards(self) -> None:
        """Sequence 10 then sequence 9 should raise SequenceRegressionError."""
        tracker = envelope.SequenceTracker()
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        env1 = _make_envelope("host1", 10, b"nonce1", now=now)
        tracker.accept(env1, now=now)

        env2 = _make_envelope("host1", 9, b"nonce2", now=now)
        with pytest.raises(envelope.SequenceRegressionError):
            tracker.accept(env2, now=now)

    def test_sequence_tracker_rejects_duplicate_nonce(self) -> None:
        """Reusing same nonce with higher seq should raise DuplicateNonceError."""
        tracker = envelope.SequenceTracker()
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        env1 = _make_envelope("host1", 5, b"nonce1", now=now)
        tracker.accept(env1, now=now)

        env2 = _make_envelope("host1", 6, b"nonce1", now=now)  # Same nonce, higher seq
        with pytest.raises(envelope.DuplicateNonceError):
            tracker.accept(env2, now=now)

    def test_sequence_tracker_rejects_expired(self) -> None:
        """Envelope with expires_at in the past should raise ExpiredCommandError."""
        tracker = envelope.SequenceTracker()

        # Create envelope that expired in the past
        creation_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        env = _make_envelope("host1", 1, b"nonce1", ttl_seconds=-100, now=creation_time)
        # Accept it at a later time
        check_time = creation_time + timedelta(seconds=200)

        with pytest.raises(envelope.ExpiredCommandError):
            tracker.accept(env, now=check_time)

    def test_sequence_tracker_isolates_hosts(self) -> None:
        """Sequence counters should be isolated per host."""
        tracker = envelope.SequenceTracker()
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        env_a1 = _make_envelope("hostA", 5, b"nonceA1", now=now)
        tracker.accept(env_a1, now=now)

        env_b1 = _make_envelope("hostB", 1, b"nonceB1", now=now)
        tracker.accept(env_b1, now=now)  # Should not raise; different host

        env_a2 = _make_envelope("hostA", 6, b"nonceA2", now=now)
        tracker.accept(env_a2, now=now)  # Should not raise; higher seq for hostA
