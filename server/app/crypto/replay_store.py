"""Persistent SQLite-backed replay protection store."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from server.app.crypto.envelope import (
    DuplicateNonceError,
    ExpiredCommandError,
    SequenceRegressionError,
)
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import envelope_pb2


class PersistentReplayStore:
    """Durable per-host sequence + nonce dedup store backed by SQLite.

    Schema:
      host_sequence(host_id TEXT PRIMARY KEY, last_sequence INTEGER NOT NULL)
      seen_nonce(host_id TEXT, nonce BLOB, seen_at INTEGER NOT NULL,
                 PRIMARY KEY(host_id, nonce))
      INDEX on seen_nonce(host_id, seen_at) for trimming.
    """

    def __init__(self, db_path: str | Path, *, nonce_window: int = 1024) -> None:
        """Initialize store with SQLite backend.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory.
            nonce_window: Maximum number of nonces to track per host.
        """
        self.nonce_window = nonce_window
        self._lock = threading.Lock()
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(
            self._db_path, isolation_level=None, check_same_thread=False
        )
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema and pragmas."""
        conn = self._conn
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")

        # Create host_sequence table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS host_sequence (
                host_id TEXT PRIMARY KEY,
                last_sequence INTEGER NOT NULL
            )
            """
        )

        # Create seen_nonce table with ROWID for stable ordering
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_nonce (
                host_id TEXT NOT NULL,
                nonce BLOB NOT NULL,
                seen_at INTEGER NOT NULL,
                PRIMARY KEY (host_id, nonce)
            )
            """
        )

        # Create index for trimming by seen_at and rowid
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_seen_nonce_seen_at
            ON seen_nonce (host_id, seen_at)
            """
        )

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> PersistentReplayStore:
        """Context manager entry."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Context manager exit."""
        self.close()

    def accept(
        self,
        env: envelope_pb2.CommandEnvelope,
        *,
        now: datetime | None = None,
    ) -> None:
        """Validate envelope under monotonic-seq + nonce-LRU + expiry rules.

        Atomic in a single transaction:
          1. SELECT last_sequence for host. If env.sequence <= last_sequence: SequenceRegressionError.
          2. SELECT 1 FROM seen_nonce WHERE host=? AND nonce=?. If exists: DuplicateNonceError.
          3. Check env.expires_at against now (UTC). If expires_at <= now: ExpiredCommandError.
          4. UPSERT host_sequence to env.sequence. INSERT seen_nonce.
          5. Trim seen_nonce for host beyond nonce_window oldest rows.

        Args:
            env: CommandEnvelope to validate and store.
            now: Current time (defaults to now(timezone.utc)).

        Raises:
            SequenceRegressionError: If sequence <= last_seen[host_id].
            DuplicateNonceError: If nonce seen within window.
            ExpiredCommandError: If expires_at <= now.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        host_id = env.host_id
        nonce = env.nonce
        sequence = env.sequence
        expires_at = env.expires_at.ToDatetime(tzinfo=timezone.utc)

        # Check expiration first (before any state changes)
        if expires_at <= now:
            raise ExpiredCommandError(f"Command expired at {expires_at}")

        with self._lock:
            conn = self._conn
            cursor = conn.cursor()

            try:
                cursor.execute("BEGIN IMMEDIATE")

                # 1. Check sequence monotonicity
                cursor.execute(
                    "SELECT last_sequence FROM host_sequence WHERE host_id = ?",
                    (host_id,),
                )
                row = cursor.fetchone()
                last_seq = row[0] if row else 0
                if sequence <= last_seq:
                    cursor.execute("ROLLBACK")
                    raise SequenceRegressionError(
                        f"Host {host_id}: sequence {sequence} <= last {last_seq}"
                    )

                # 2. Check nonce dedup
                cursor.execute(
                    "SELECT 1 FROM seen_nonce WHERE host_id = ? AND nonce = ?",
                    (host_id, nonce),
                )
                if cursor.fetchone():
                    cursor.execute("ROLLBACK")
                    raise DuplicateNonceError(
                        f"Host {host_id}: nonce {nonce!r} already seen"
                    )

                # 4. UPSERT host_sequence
                cursor.execute(
                    """
                    INSERT INTO host_sequence (host_id, last_sequence)
                    VALUES (?, ?)
                    ON CONFLICT(host_id) DO UPDATE SET last_sequence = excluded.last_sequence
                    """,
                    (host_id, sequence),
                )

                # Insert seen_nonce
                seen_at = int(now.timestamp() * 1_000_000)
                cursor.execute(
                    "INSERT INTO seen_nonce (host_id, nonce, seen_at) VALUES (?, ?, ?)",
                    (host_id, nonce, seen_at),
                )

                # 5. Trim seen_nonce for host beyond nonce_window oldest rows
                # Keep the newest nonce_window rows by (seen_at, rowid) descending
                cursor.execute(
                    """
                    DELETE FROM seen_nonce
                    WHERE host_id = ?
                    AND (host_id, nonce) NOT IN (
                        SELECT host_id, nonce FROM seen_nonce
                        WHERE host_id = ?
                        ORDER BY seen_at DESC, rowid DESC
                        LIMIT ?
                    )
                    """,
                    (host_id, host_id, self.nonce_window),
                )

                cursor.execute("COMMIT")
            except (SequenceRegressionError, DuplicateNonceError, ExpiredCommandError):
                raise
            except Exception:
                cursor.execute("ROLLBACK")
                raise

    def last_sequence(self, host_id: str) -> int:
        """Return last accepted sequence for host, or 0 if unknown.

        Args:
            host_id: Host identifier.

        Returns:
            Last sequence number, or 0 if no sequence recorded yet.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT last_sequence FROM host_sequence WHERE host_id = ?",
                (host_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def known_nonces(self, host_id: str) -> int:
        """Return current count of stored nonces for host.

        Args:
            host_id: Host identifier.

        Returns:
            Count of nonces currently in the window for this host.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM seen_nonce WHERE host_id = ?",
                (host_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
