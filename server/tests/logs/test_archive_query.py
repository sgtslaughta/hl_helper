"""Tests for archive query manager."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from server.app.logs.archive_query import ArchiveQueryManager
from server.app.logs.retention import LocalSink


class TestArchiveQueryManager:
    """Test ArchiveQueryManager."""

    @pytest.mark.asyncio
    async def test_submit_returns_job_id(self, tmp_path: Path) -> None:
        """Test submit returns a valid job ID."""
        sink = LocalSink(tmp_path)
        sink.write_ndjson_gz(
            "agent_logs/2026/01/host_h1.ndjson.gz",
            iter([b'{"action":"task.exec.completed","host_id":"h1"}\n']),
        )
        mgr = ArchiveQueryManager(sink)
        job_id = await mgr.submit(from_ts=None, to_ts=None, host_ids=["h1"])
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    @pytest.mark.asyncio
    async def test_job_completes_with_matching_lines(self, tmp_path: Path) -> None:
        """Test job completes and returns matching lines."""
        sink = LocalSink(tmp_path)
        sink.write_ndjson_gz(
            "agent_logs/2026/01/host_h1.ndjson.gz",
            iter([
                b'{"action":"task.exec.completed","host_id":"h1"}\n',
                b'{"action":"update.swap.failed","host_id":"h1"}\n',
            ]),
        )
        mgr = ArchiveQueryManager(sink)
        job_id = await mgr.submit(
            from_ts=None, to_ts=None, host_ids=["h1"], action="task.exec.completed"
        )

        # Poll until complete
        for _ in range(50):
            s = mgr.status(job_id)
            if s["state"] == "complete":
                break
            await asyncio.sleep(0.05)

        s = mgr.status(job_id)
        assert s["state"] == "complete"
        assert len(s["results"]) == 1
        assert s["results"][0]["action"] == "task.exec.completed"

    @pytest.mark.asyncio
    async def test_no_matches_returns_empty_results(self, tmp_path: Path) -> None:
        """Test query with no matches returns empty results."""
        sink = LocalSink(tmp_path)
        sink.write_ndjson_gz(
            "agent_logs/2026/01/host_h1.ndjson.gz",
            iter([b'{"action":"task.exec.completed","host_id":"h1"}\n']),
        )
        mgr = ArchiveQueryManager(sink)
        job_id = await mgr.submit(
            from_ts=None, to_ts=None, host_ids=["h1"], action="nonexistent"
        )

        # Poll until complete
        for _ in range(50):
            s = mgr.status(job_id)
            if s["state"] == "complete":
                break
            await asyncio.sleep(0.05)

        s = mgr.status(job_id)
        assert s["state"] == "complete"
        assert len(s["results"]) == 0

    @pytest.mark.asyncio
    async def test_host_id_filtering(self, tmp_path: Path) -> None:
        """Test filtering by host_id."""
        sink = LocalSink(tmp_path)
        sink.write_ndjson_gz(
            "agent_logs/2026/01/host_h1.ndjson.gz",
            iter([b'{"action":"task.exec.completed","host_id":"h1"}\n']),
        )
        sink.write_ndjson_gz(
            "agent_logs/2026/01/host_h2.ndjson.gz",
            iter([b'{"action":"task.exec.completed","host_id":"h2"}\n']),
        )
        mgr = ArchiveQueryManager(sink)
        job_id = await mgr.submit(from_ts=None, to_ts=None, host_ids=["h1"])

        # Poll until complete
        for _ in range(50):
            s = mgr.status(job_id)
            if s["state"] == "complete":
                break
            await asyncio.sleep(0.05)

        s = mgr.status(job_id)
        assert s["state"] == "complete"
        assert len(s["results"]) == 1
        assert s["results"][0]["host_id"] == "h1"

    @pytest.mark.asyncio
    async def test_invalid_job_id(self, tmp_path: Path) -> None:
        """Test status of invalid job ID."""
        sink = LocalSink(tmp_path)
        mgr = ArchiveQueryManager(sink)
        s = mgr.status("invalid-job-id")
        assert s["state"] == "error" or "error" in s

    @pytest.mark.asyncio
    async def test_level_filtering(self, tmp_path: Path) -> None:
        """Test filtering by log level."""
        sink = LocalSink(tmp_path)
        sink.write_ndjson_gz(
            "agent_logs/2026/01/host_h1.ndjson.gz",
            iter([
                b'{"action":"task.exec.completed","host_id":"h1","level":20}\n',
                b'{"action":"task.exec.failed","host_id":"h1","level":40}\n',
            ]),
        )
        mgr = ArchiveQueryManager(sink)
        job_id = await mgr.submit(
            from_ts=None, to_ts=None, host_ids=["h1"], level=20
        )

        # Poll until complete
        for _ in range(50):
            s = mgr.status(job_id)
            if s["state"] == "complete":
                break
            await asyncio.sleep(0.05)

        s = mgr.status(job_id)
        assert s["state"] == "complete"
        assert len(s["results"]) == 1
        assert s["results"][0]["level"] == 20
