"""Test agent_logs and agent_log_policies tables."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, create_engine


def test_agent_logs_table_exists(tmp_path: Path) -> None:
    """Verify agent_logs table exists with all required columns."""
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    eng = create_engine(f"sqlite:///{db}")
    insp = inspect(eng)
    assert "agent_logs" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("agent_logs")}
    expected = {
        "host_id",
        "agent_id",
        "agent_session_id",
        "seq",
        "ts",
        "level",
        "action",
        "category",
        "outcome",
        "labels",
        "details",
        "error",
        "ingested_at",
    }
    assert expected.issubset(cols)


def test_agent_log_policies_table_exists(tmp_path: Path) -> None:
    """Verify agent_log_policies table exists."""
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    eng = create_engine(f"sqlite:///{db}")
    insp = inspect(eng)
    assert "agent_log_policies" in insp.get_table_names()


def test_unique_session_seq(tmp_path: Path) -> None:
    """Verify agent_logs has unique constraint on (agent_session_id, seq)."""
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    eng = create_engine(f"sqlite:///{db}")
    insp = inspect(eng)
    uniques = insp.get_unique_constraints("agent_logs")
    cols = [tuple(u["column_names"]) for u in uniques]
    assert ("agent_session_id", "seq") in cols


def test_agent_log_policies_unique_scope(tmp_path: Path) -> None:
    """Verify agent_log_policies has unique constraint on scope."""
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    eng = create_engine(f"sqlite:///{db}")
    insp = inspect(eng)
    uniques = insp.get_unique_constraints("agent_log_policies")
    cols = [tuple(u["column_names"]) for u in uniques]
    assert ("scope",) in cols
