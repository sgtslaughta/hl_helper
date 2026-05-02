"""Verify Alembic migration applies cleanly to a temp SQLite and matches model metadata."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, create_engine


def test_alembic_upgrade_head_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    repo = Path(__file__).resolve().parents[3]  # /home/user/code/hl_helper
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    # Inspect resulting DB.
    eng = create_engine(f"sqlite:///{db}")
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    expected = {
        "hosts",
        "enrollment_tokens",
        "commands",
        "results",
        "audit_entries",
        "audit_checkpoints",
        "alembic_version",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_alembic_downgrade_to_base(tmp_path: Path) -> None:
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    repo = Path(__file__).resolve().parents[3]

    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                        cwd=repo, env=env, capture_output=True, text=True)
    assert up.returncode == 0, up.stderr

    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"],
                          cwd=repo, env=env, capture_output=True, text=True)
    assert down.returncode == 0, down.stderr

    eng = create_engine(f"sqlite:///{db}")
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    # Only alembic_version remains after downgrade to base.
    assert tables == {"alembic_version"}
