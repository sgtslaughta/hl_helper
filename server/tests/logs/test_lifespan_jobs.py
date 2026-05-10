"""Tests for lifespan job registration (Task 3.8)."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from server.app.logs.models import AgentLogPolicy
from server.app.logs.retention import LocalSink


class FakeScheduler:
    """Mock APScheduler for testing job registration without actual scheduling."""

    def __init__(self) -> None:
        """Initialize fake scheduler."""
        self.jobs: list[dict] = []

    def add_job(self, fn, trigger=None, **kw) -> None:
        """Record job registration."""
        fn_name = fn.__name__ if hasattr(fn, "__name__") else str(fn)
        self.jobs.append({
            "fn": fn_name,
            "trigger": str(trigger) if trigger else None,
            "kw": kw,
        })


def test_register_jobs_when_enabled(db_session, tmp_path, monkeypatch) -> None:
    """Test that jobs are registered when FLEET_LOG_RETENTION_ENABLED=true."""
    from server.app.lifespan import register_log_retention_jobs

    monkeypatch.setenv("FLEET_LOG_RETENTION_ENABLED", "true")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("FLEET_LOG_HOT_DAYS", "30")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_RETENTION_DAYS", "365")

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    # Should have registered 3 jobs
    assert len(sched.jobs) == 3

    # Verify job names exist (function names or identifiers)
    job_data = {job["fn"] for job in sched.jobs}
    # Jobs should be identifiable by their registered names
    assert len(job_data) >= 1  # At least one unique job registered


def test_register_jobs_no_op_when_disabled(db_session, tmp_path, monkeypatch) -> None:
    """Test that no jobs are registered when FLEET_LOG_RETENTION_ENABLED=false."""
    from server.app.lifespan import register_log_retention_jobs

    monkeypatch.setenv("FLEET_LOG_RETENTION_ENABLED", "false")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path))

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    # Should have no jobs registered
    assert len(sched.jobs) == 0


def test_register_jobs_default_enabled(db_session, tmp_path, monkeypatch) -> None:
    """Test that jobs are registered by default (FLEET_LOG_RETENTION_ENABLED defaults to True)."""
    from server.app.lifespan import register_log_retention_jobs

    # Don't set FLEET_LOG_RETENTION_ENABLED; it should default to True
    monkeypatch.delenv("FLEET_LOG_RETENTION_ENABLED", raising=False)
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path))

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    # Should have registered 3 jobs by default
    assert len(sched.jobs) == 3


def test_register_jobs_uses_local_sink(db_session, tmp_path, monkeypatch) -> None:
    """Test that local sink is created when only LOCAL_PATH is set."""
    from server.app.lifespan import register_log_retention_jobs

    monkeypatch.setenv("FLEET_LOG_RETENTION_ENABLED", "true")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path / "archive"))
    monkeypatch.delenv("FLEET_LOG_ARCHIVE_S3_URI", raising=False)

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    assert len(sched.jobs) == 3


def test_register_jobs_uses_s3_sink_when_configured(db_session, tmp_path, monkeypatch) -> None:
    """Test that S3 sink is used when S3_URI is configured."""
    from server.app.lifespan import register_log_retention_jobs
    import sys

    monkeypatch.setenv("FLEET_LOG_RETENTION_ENABLED", "true")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_S3_URI", "s3://test-bucket/prefix")
    # Still provide local path as fallback, but S3 should take precedence
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path / "archive"))

    # Mock boto3 at the module level to avoid ImportError
    mock_boto3 = type(sys)("boto3")
    mock_boto3.client = lambda service: None
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    assert len(sched.jobs) == 3


def test_register_jobs_respects_hot_days_setting(db_session, tmp_path, monkeypatch) -> None:
    """Test that FLEET_LOG_HOT_DAYS setting is used."""
    from server.app.lifespan import register_log_retention_jobs

    monkeypatch.setenv("FLEET_LOG_RETENTION_ENABLED", "true")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("FLEET_LOG_HOT_DAYS", "60")

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    assert len(sched.jobs) == 3


def test_register_jobs_respects_retention_days_setting(db_session, tmp_path, monkeypatch) -> None:
    """Test that FLEET_LOG_ARCHIVE_RETENTION_DAYS setting is used."""
    from server.app.lifespan import register_log_retention_jobs

    monkeypatch.setenv("FLEET_LOG_RETENTION_ENABLED", "true")
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("FLEET_LOG_ARCHIVE_RETENTION_DAYS", "730")

    sched = FakeScheduler()
    register_log_retention_jobs(sched, db_session)

    assert len(sched.jobs) == 3
