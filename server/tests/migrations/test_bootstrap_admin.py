"""Test bootstrap admin seeding migration."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


def test_no_admin_seeded_without_env(tmp_path: Path) -> None:
    """Test that no admin is seeded when FLEET_BOOTSTRAP_ADMIN_EMAIL is unset."""
    db = tmp_path / "fleet_test.db"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    # Ensure env is unset
    env.pop("FLEET_BOOTSTRAP_ADMIN_EMAIL", None)

    repo = Path(__file__).resolve().parents[3]  # /home/user/code/hl_helper
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    # Query bindings — should be none
    eng = create_engine(f"sqlite:///{db}")
    with eng.connect() as conn:
        row = conn.execute(text("SELECT COUNT(*) FROM bindings")).scalar()
        assert row == 0, f"Expected 0 bindings, found {row}"


def test_admin_seeded_with_env(tmp_path: Path) -> None:
    """Test that admin is seeded when FLEET_BOOTSTRAP_ADMIN_EMAIL is set."""
    db = tmp_path / "fleet_test.db"
    admin_email = "admin@test"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    env["FLEET_BOOTSTRAP_ADMIN_EMAIL"] = admin_email

    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"

    # Query bindings and user
    eng = create_engine(f"sqlite:///{db}")
    with eng.connect() as conn:
        # Should have exactly one binding with admin role
        binding_row = conn.execute(
            text("SELECT COUNT(*) FROM bindings")
        ).scalar()
        assert binding_row == 1, f"Expected 1 binding, found {binding_row}"

        # Get the binding and verify scope
        binding_data = conn.execute(
            text("SELECT principal_type, role_id, scope_kind, scope_value FROM bindings")
        ).first()
        assert binding_data is not None
        assert binding_data[0] == "user", f"Expected principal_type='user', got {binding_data[0]}"
        assert binding_data[2] == "global", f"Expected scope_kind='global', got {binding_data[2]}"

        # Verify admin role exists
        admin_role = conn.execute(
            text("SELECT id FROM roles WHERE name = 'admin'")
        ).scalar()
        assert admin_role == binding_data[1], "Binding should reference admin role"

        # Verify user exists with correct email
        user_row = conn.execute(
            text("SELECT id, email, kind FROM users WHERE email = :email"),
            {"email": admin_email},
        ).first()
        assert user_row is not None, f"User with email {admin_email} should exist"
        assert user_row[1] == admin_email
        assert user_row[2] == "local", f"Expected kind='local', got {user_row[2]}"


def test_admin_seeded_idempotent(tmp_path: Path) -> None:
    """Test that running the migration twice is idempotent."""
    db = tmp_path / "fleet_test.db"
    admin_email = "admin@test"
    env = os.environ.copy()
    env["FLEET_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    env["FLEET_BOOTSTRAP_ADMIN_EMAIL"] = admin_email

    repo = Path(__file__).resolve().parents[3]

    # Run upgrade to head
    result1 = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result1.returncode == 0, f"alembic upgrade failed:\n{result1.stdout}\n{result1.stderr}"

    # Run downgrade then upgrade again
    result2 = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0012_command_idempotency_key"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result2.returncode == 0, f"alembic downgrade failed:\n{result2.stdout}\n{result2.stderr}"

    result3 = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert result3.returncode == 0, f"alembic upgrade failed:\n{result3.stdout}\n{result3.stderr}"

    # Verify still only one binding/user
    eng = create_engine(f"sqlite:///{db}")
    with eng.connect() as conn:
        binding_count = conn.execute(text("SELECT COUNT(*) FROM bindings")).scalar()
        assert binding_count == 1, f"Expected 1 binding, found {binding_count}"

        user_count = conn.execute(
            text("SELECT COUNT(*) FROM users WHERE email = :email"),
            {"email": admin_email},
        ).scalar()
        assert user_count == 1, f"Expected 1 user, found {user_count}"
