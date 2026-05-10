"""Tests for log retention (archive and purge)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from server.app.logs.models import AgentLog
from server.app.logs.retention import LocalSink, archive_once, purge_archive


def _seed_row(
    db_session,
    *,
    host_id: str,
    seq: int,
    age_days: int = 0,
    when: datetime | None = None,
) -> AgentLog:
    """Create and persist an agent log row."""
    ts = when or (datetime.now(timezone.utc) - timedelta(days=age_days))
    row = AgentLog(
        host_id=host_id,
        agent_id="a",
        agent_session_id="s",
        agent_version="0.4.1",
        seq=seq,
        ts=ts,
        level=20,
        action="task.exec.completed",
        category="task",
        outcome=1,
        message="ok",
        labels={},
        details={"rc": 0},
    )
    db_session.add(row)
    db_session.commit()
    return row


class TestLocalSink:
    """Test LocalSink implementation."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """Test write and read NDJSON.GZ."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("k/test.ndjson.gz", iter([b'{"a":1}\n', b'{"b":2}\n']))
        out = list(sink.read_ndjson_gz("k/test.ndjson.gz"))
        assert out == [b'{"a":1}\n', b'{"b":2}\n']

    def test_list_keys(self, tmp_path: Path) -> None:
        """Test listing keys with prefix."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("agent_logs/2026/01/host_h1.ndjson.gz", iter([b'{}\n']))
        sink.write_ndjson_gz("agent_logs/2026/02/host_h2.ndjson.gz", iter([b'{}\n']))
        sink.write_ndjson_gz("other/data.ndjson.gz", iter([b'{}\n']))
        keys = sink.list_keys("agent_logs/")
        assert "agent_logs/2026/01/host_h1.ndjson.gz" in keys
        assert "agent_logs/2026/02/host_h2.ndjson.gz" in keys
        assert "other/data.ndjson.gz" not in keys

    def test_delete(self, tmp_path: Path) -> None:
        """Test delete operation."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("k/test.ndjson.gz", iter([b'{}\n']))
        assert (tmp_path / "archive" / "k" / "test.ndjson.gz").exists()
        sink.delete("k/test.ndjson.gz")
        assert not (tmp_path / "archive" / "k" / "test.ndjson.gz").exists()

    def test_stat(self, tmp_path: Path) -> None:
        """Test stat operation."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("k/test.ndjson.gz", iter([b'{}\n']))
        stat = sink.stat("k/test.ndjson.gz")
        assert "size" in stat
        assert "mtime" in stat
        assert stat["size"] > 0
        assert isinstance(stat["mtime"], datetime)


class TestArchiveOnce:
    """Test archive_once function."""

    def test_moves_old_rows(self, db_session, tmp_path: Path) -> None:
        """Test archiving rows older than hot_days."""
        sink = LocalSink(tmp_path / "archive")
        _seed_row(db_session, host_id="h1", seq=1, age_days=40)
        _seed_row(db_session, host_id="h1", seq=2, age_days=40)
        _seed_row(db_session, host_id="h1", seq=3, age_days=5)

        result = archive_once(db_session, sink, hot_days=30)

        assert result["archived_rows"] == 2
        assert result["files_written"] >= 1

        remaining = db_session.execute(select(AgentLog)).scalars().all()
        assert {r.seq for r in remaining} == {3}

    def test_no_op_when_empty(self, db_session, tmp_path: Path) -> None:
        """Test no-op when no old rows exist."""
        sink = LocalSink(tmp_path / "archive")
        result = archive_once(db_session, sink, hot_days=30)
        assert result["archived_rows"] == 0
        assert result["files_written"] == 0

    def test_no_op_when_all_rows_hot(self, db_session, tmp_path: Path) -> None:
        """Test no-op when all rows are within hot window."""
        sink = LocalSink(tmp_path / "archive")
        _seed_row(db_session, host_id="h1", seq=1, age_days=5)
        _seed_row(db_session, host_id="h1", seq=2, age_days=10)
        result = archive_once(db_session, sink, hot_days=30)
        assert result["archived_rows"] == 0
        assert result["files_written"] == 0
        remaining = db_session.execute(select(AgentLog)).scalars().all()
        assert len(remaining) == 2

    def test_groups_by_host_and_month(self, db_session, tmp_path: Path) -> None:
        """Test rows grouped by host_id and month."""
        sink = LocalSink(tmp_path / "archive")
        jan_date = datetime(2026, 1, 15, tzinfo=timezone.utc)
        feb_date = datetime(2026, 2, 15, tzinfo=timezone.utc)
        _seed_row(db_session, host_id="h1", seq=1, when=jan_date - timedelta(days=40))
        _seed_row(db_session, host_id="h1", seq=2, when=feb_date - timedelta(days=40))
        _seed_row(db_session, host_id="h2", seq=3, when=jan_date - timedelta(days=40))

        result = archive_once(db_session, sink, hot_days=30)

        assert result["archived_rows"] == 3
        # Should have 3 files: h1/2026/01, h1/2026/02, h2/2026/01
        keys = sink.list_keys("agent_logs/")
        assert len(keys) == 3

    def test_double_run_appends(self, db_session, tmp_path: Path) -> None:
        """Test idempotent double-run appends to existing archive files."""
        sink = LocalSink(tmp_path / "archive")
        _seed_row(db_session, host_id="h1", seq=1, age_days=40)
        archive_once(db_session, sink, hot_days=30)

        # Seed another row for the same (host, month)
        _seed_row(db_session, host_id="h1", seq=2, age_days=40)
        archive_once(db_session, sink, hot_days=30)

        # Both rows should exist in archive
        keys = [k for k in sink.list_keys("agent_logs/") if "host_h1" in k]
        assert keys
        lines = list(sink.read_ndjson_gz(keys[0]))
        assert len(lines) == 2

    def test_archived_rows_are_valid_json(self, db_session, tmp_path: Path) -> None:
        """Test that archived rows are valid NDJSON."""
        sink = LocalSink(tmp_path / "archive")
        _seed_row(db_session, host_id="h1", seq=1, age_days=40)
        archive_once(db_session, sink, hot_days=30)

        keys = sink.list_keys("agent_logs/")
        assert len(keys) >= 1
        lines = list(sink.read_ndjson_gz(keys[0]))
        for line in lines:
            obj = json.loads(line.decode("utf-8"))
            assert "host_id" in obj
            assert "seq" in obj
            assert "ts" in obj


class TestPurgeArchive:
    """Test purge_archive function."""

    def test_removes_old_files(self, tmp_path: Path) -> None:
        """Test purging files older than retention_days."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("agent_logs/2024/01/host_h1.ndjson.gz", iter([b'{}\n']))
        p = tmp_path / "archive" / "agent_logs" / "2024" / "01" / "host_h1.ndjson.gz"

        # Backdate file by 400 days
        old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).timestamp()
        os.utime(p, (old_ts, old_ts))

        n = purge_archive(sink, retention_days=365)
        assert n == 1
        assert not p.exists()

    def test_keeps_recent_files(self, tmp_path: Path) -> None:
        """Test that recent files are kept."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("agent_logs/2026/04/host_h1.ndjson.gz", iter([b'{}\n']))
        p = tmp_path / "archive" / "agent_logs" / "2026" / "04" / "host_h1.ndjson.gz"

        # Backdate file by 100 days
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).timestamp()
        os.utime(p, (old_ts, old_ts))

        n = purge_archive(sink, retention_days=365)
        assert n == 0
        assert p.exists()

    def test_respects_compliance_hold(self, tmp_path: Path) -> None:
        """Test that files for compliance-held hosts are not deleted."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz(
            "agent_logs/2024/01/host_hold.ndjson.gz", iter([b'{}\n'])
        )
        p = tmp_path / "archive" / "agent_logs" / "2024" / "01" / "host_hold.ndjson.gz"

        old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).timestamp()
        os.utime(p, (old_ts, old_ts))

        n = purge_archive(
            sink, retention_days=365, compliance_hold_host_ids={"hold"}
        )
        assert n == 0
        assert p.exists()

    def test_mixed_old_and_new(self, tmp_path: Path) -> None:
        """Test purging with mixed old and new files."""
        sink = LocalSink(tmp_path / "archive")
        sink.write_ndjson_gz("agent_logs/2024/01/host_old.ndjson.gz", iter([b'{}\n']))
        sink.write_ndjson_gz("agent_logs/2026/04/host_new.ndjson.gz", iter([b'{}\n']))

        old_p = (
            tmp_path / "archive" / "agent_logs" / "2024" / "01" / "host_old.ndjson.gz"
        )
        new_p = (
            tmp_path / "archive" / "agent_logs" / "2026" / "04" / "host_new.ndjson.gz"
        )

        # Backdate old file by 400 days
        old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).timestamp()
        os.utime(old_p, (old_ts, old_ts))

        n = purge_archive(sink, retention_days=365)
        assert n == 1
        assert not old_p.exists()
        assert new_p.exists()
