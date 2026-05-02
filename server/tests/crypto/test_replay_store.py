"""Tests for server.app.crypto.replay_store: persistent SQLite replay protection."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from server.app.crypto.envelope import (
    DuplicateNonceError,
    ExpiredCommandError,
    SequenceRegressionError,
)
from server.app.crypto.replay_store import ClockSkewError, PersistentReplayStore
from server.app.grpc._pb import fleet  # noqa: F401  triggers sys.path injection
from server.app.grpc._pb.fleet.v1 import envelope_pb2


def make_env(
    host: str,
    seq: int,
    nonce: bytes,
    *,
    ttl_s: int = 600,
    now: datetime | None = None,
) -> envelope_pb2.CommandEnvelope:
    """Factory to build a CommandEnvelope with PkgUpdate payload."""
    if now is None:
        now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_s)

    env = envelope_pb2.CommandEnvelope()
    env.command_id = f"cmd-{host}-{seq}"
    env.host_id = host
    env.sequence = seq
    env.nonce = nonce
    env.issued_at.FromDatetime(now)
    env.expires_at.FromDatetime(expires)
    env.issued_by = "test-server"

    # Set PkgUpdate payload
    env.pkg_update.classes.append("base")
    env.pkg_update.dry_run = False

    return env


class TestPersistentReplayStore:
    """Tests for PersistentReplayStore class."""

    def test_accepts_first_envelope(self, tmp_path: Path) -> None:
        """Fresh store, env seq=1 nonce=b'a' expires_at=+10min → no raise."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        env = make_env("host1", 1, b"a", ttl_s=600, now=now)

        store = PersistentReplayStore(db_path)
        store.accept(env, now=now)
        assert store.last_sequence("host1") == 1
        assert store.known_nonces("host1") == 1
        store.close()

    def test_rejects_replay_same_sequence(self, tmp_path: Path) -> None:
        """Accept seq=5; replay seq=5 → SequenceRegressionError."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)
        env1 = make_env("host1", 5, b"nonce1", now=now)
        store.accept(env1, now=now)

        env2 = make_env("host1", 5, b"nonce2", now=now)
        with pytest.raises(SequenceRegressionError):
            store.accept(env2, now=now)
        store.close()

    def test_rejects_backwards_sequence(self, tmp_path: Path) -> None:
        """Accept seq=10; then seq=9 → SequenceRegressionError."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)
        env1 = make_env("host1", 10, b"nonce1", now=now)
        store.accept(env1, now=now)

        env2 = make_env("host1", 9, b"nonce2", now=now)
        with pytest.raises(SequenceRegressionError):
            store.accept(env2, now=now)
        store.close()

    def test_accepts_increasing_sequence(self, tmp_path: Path) -> None:
        """Seq=1,2,3 same host → all ok; last_sequence=3."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)
        for seq in [1, 2, 3]:
            env = make_env("host1", seq, f"nonce{seq}".encode(), now=now)
            store.accept(env, now=now)
        assert store.last_sequence("host1") == 3
        store.close()

    def test_rejects_duplicate_nonce_within_window(self, tmp_path: Path) -> None:
        """Seq=1 nonce=N; seq=2 nonce=N → DuplicateNonceError."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)
        env1 = make_env("host1", 1, b"nonce_reused", now=now)
        store.accept(env1, now=now)

        env2 = make_env("host1", 2, b"nonce_reused", now=now)
        with pytest.raises(DuplicateNonceError):
            store.accept(env2, now=now)
        store.close()

    def test_isolates_hosts(self, tmp_path: Path) -> None:
        """Host A seq=5 doesn't block host B seq=1."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)
        env_a = make_env("hostA", 5, b"nonceA", now=now)
        store.accept(env_a, now=now)

        env_b = make_env("hostB", 1, b"nonceB", now=now)
        store.accept(env_b, now=now)  # Should not raise; different host

        assert store.last_sequence("hostA") == 5
        assert store.last_sequence("hostB") == 1
        store.close()

    def test_rejects_expired(self, tmp_path: Path) -> None:
        """Expires_at = now - 1s → ExpiredCommandError; state unchanged."""
        db_path = tmp_path / "test.db"
        creation_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)

        # Accept a valid envelope first
        env1 = make_env("host1", 1, b"nonce1", ttl_s=600, now=creation_time)
        store.accept(env1, now=creation_time)

        # Try to accept an expired envelope
        check_time = creation_time + timedelta(seconds=700)
        env2 = make_env("host1", 2, b"nonce2", ttl_s=600, now=creation_time)
        with pytest.raises(ExpiredCommandError):
            store.accept(env2, now=check_time)

        # Verify state is unchanged (seq should still be 1)
        assert store.last_sequence("host1") == 1
        store.close()

    def test_persistence_across_reopen(self, tmp_path: Path) -> None:
        """Open store, accept seq=7; close; reopen same path → last_sequence=7."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store1 = PersistentReplayStore(db_path)
        env = make_env("host1", 7, b"nonce7", now=now)
        store1.accept(env, now=now)
        store1.close()

        # Reopen and verify persistence
        store2 = PersistentReplayStore(db_path)
        assert store2.last_sequence("host1") == 7

        # Also verify replay is still blocked
        env_replay = make_env("host1", 7, b"nonce_new", now=now)
        with pytest.raises(SequenceRegressionError):
            store2.accept(env_replay, now=now)
        store2.close()

    def test_nonce_window_trims_oldest(self, tmp_path: Path) -> None:
        """Nonce_window=3; insert 5 distinct nonces; known_nonces==3 after."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path, nonce_window=3)

        # Insert 5 nonces
        for seq in range(1, 6):
            env = make_env("host1", seq, f"nonce{seq}".encode(), now=now)
            store.accept(env, now=now)

        # Should have only 3 nonces (oldest 2 trimmed)
        assert store.known_nonces("host1") == 3

        # Oldest nonce (nonce1) should be reusable without raising DuplicateNonceError
        env_reuse = make_env("host1", 6, b"nonce1", now=now)
        store.accept(env_reuse, now=now)  # Should not raise
        store.close()

    def test_context_manager_closes_connection(self, tmp_path: Path) -> None:
        """With PersistentReplayStore(p) context manager closes after exit."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        with PersistentReplayStore(db_path) as store:
            env = make_env("host1", 1, b"nonce1", now=now)
            store.accept(env, now=now)

        # After exit, attempting to use should raise
        with pytest.raises(sqlite3.ProgrammingError):
            store.accept(env, now=now)

    def test_concurrent_accepts_serialized(self, tmp_path: Path) -> None:
        """Spawn 2 threads, each inserts sequences to independent hosts."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path)
        start_barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def thread_worker(host_id: str, sequences: list[int]) -> None:
            try:
                start_barrier.wait()  # Wait for both threads
                for seq in sequences:
                    env = make_env(host_id, seq, f"nonce{seq}".encode(), now=now)
                    store.accept(env, now=now)
            except Exception as e:
                errors.append(e)

        # Thread 1: hostA with 1,2,3
        # Thread 2: hostB with 1,2,3
        # No sequence conflicts because different hosts
        t1 = threading.Thread(target=thread_worker, args=("hostA", [1, 2, 3]))
        t2 = threading.Thread(target=thread_worker, args=("hostB", [1, 2, 3]))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert store.last_sequence("hostA") == 3
        assert store.last_sequence("hostB") == 3
        store.close()

    def test_memory_store_with_colon_memory(self, tmp_path: Path) -> None:
        """Test that :memory: works (no persistence needed for this test)."""
        store = PersistentReplayStore(":memory:")
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        env = make_env("host1", 1, b"nonce1", now=now)
        store.accept(env, now=now)
        assert store.last_sequence("host1") == 1
        store.close()

    def test_rejects_command_issued_too_far_in_future(self, tmp_path: Path) -> None:
        """Env with issued_at = now + 5min, store with default 60s tolerance → ClockSkewError."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        issued_time = now + timedelta(seconds=300)  # 5 minutes in future

        store = PersistentReplayStore(db_path)
        env = make_env("host1", 1, b"nonce1", ttl_s=600, now=issued_time)
        env.issued_at.FromDatetime(issued_time)

        with pytest.raises(ClockSkewError, match="too far in future"):
            store.accept(env, now=now)
        store.close()

    def test_accepts_command_within_skew_tolerance(self, tmp_path: Path) -> None:
        """Env with issued_at = now + 30s, default 60s tolerance → ok."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        issued_time = now + timedelta(seconds=30)  # 30 seconds in future

        store = PersistentReplayStore(db_path)
        env = make_env("host1", 1, b"nonce1", ttl_s=600, now=issued_time)
        env.issued_at.FromDatetime(issued_time)

        store.accept(env, now=now)  # Should not raise
        assert store.last_sequence("host1") == 1
        store.close()

    def test_skew_tolerance_configurable(self, tmp_path: Path) -> None:
        """Store with skew_tolerance_s=300; issued_at = now+200s → ok; now+400s → ClockSkewError."""
        db_path = tmp_path / "test.db"
        now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        store = PersistentReplayStore(db_path, skew_tolerance_s=300)

        # Test 1: issued_at = now + 200s (within 300s tolerance)
        issued_time_ok = now + timedelta(seconds=200)
        env_ok = make_env("host1", 1, b"nonce1", ttl_s=600, now=issued_time_ok)
        env_ok.issued_at.FromDatetime(issued_time_ok)
        store.accept(env_ok, now=now)  # Should not raise
        assert store.last_sequence("host1") == 1

        # Test 2: issued_at = now + 400s (exceeds 300s tolerance)
        issued_time_bad = now + timedelta(seconds=400)
        env_bad = make_env("host1", 2, b"nonce2", ttl_s=600, now=issued_time_bad)
        env_bad.issued_at.FromDatetime(issued_time_bad)
        with pytest.raises(ClockSkewError, match="too far in future"):
            store.accept(env_bad, now=now)
        store.close()
