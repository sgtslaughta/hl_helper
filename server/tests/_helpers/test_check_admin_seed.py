"""Test check_admin_seed helper script."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from server.app.models import Base


def test_check_admin_seed_success_with_admin(tmp_path: Path) -> None:
    """Test check_admin_seed exits 0 when admin user + binding exists."""
    db = tmp_path / "fleet.db"
    admin_email = "ci-admin@example.test"

    # Set up a real DB with the expected schema and data
    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # Insert admin role
        admin_role_id = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO roles (id, name, built_in, permissions) VALUES (:id, :name, 1, '[]')"
            ),
            {"id": admin_role_id, "name": "admin"},
        )

        # Insert user
        user_id = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO users (id, email, kind, disabled) VALUES (:id, :email, :kind, 0)"
            ),
            {"id": user_id, "email": admin_email, "kind": "local"},
        )

        # Insert admin binding with global scope
        binding_id = str(uuid4())
        scope_hash = "abc123"  # Dummy hash
        conn.execute(
            text(
                """
                INSERT INTO bindings
                  (id, principal_type, principal_id, role_id, scope_kind, scope_value, scope_hash)
                VALUES (:id, :ptype, :pid, :rid, :kind, :value, :sh)
                """
            ),
            {
                "id": binding_id,
                "ptype": "user",
                "pid": user_id,
                "rid": admin_role_id,
                "kind": "global",
                "value": json.dumps({}),
                "sh": scope_hash,
            },
        )

    engine.dispose()

    # Run the helper script
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.tests._helpers.check_admin_seed",
            "--db-url",
            f"sqlite:///{db}",
            "--email",
            admin_email,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
    assert "PASS" in result.stdout
    assert admin_email in result.stdout


def test_check_admin_seed_fail_missing_user(tmp_path: Path) -> None:
    """Test check_admin_seed exits 1 when user doesn't exist."""
    db = tmp_path / "fleet.db"
    admin_email = "missing@example.test"

    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    engine.dispose()

    # Run the helper script (no user was inserted)
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.tests._helpers.check_admin_seed",
            "--db-url",
            f"sqlite:///{db}",
            "--email",
            admin_email,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
    assert "FAIL" in result.stderr


def test_check_admin_seed_fail_missing_binding(tmp_path: Path) -> None:
    """Test check_admin_seed exits 1 when binding doesn't exist."""
    db = tmp_path / "fleet.db"
    admin_email = "no-binding@example.test"

    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # Insert user but no binding
        user_id = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO users (id, email, kind, disabled) VALUES (:id, :email, :kind, 0)"
            ),
            {"id": user_id, "email": admin_email, "kind": "local"},
        )

    engine.dispose()

    # Run the helper script
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.tests._helpers.check_admin_seed",
            "--db-url",
            f"sqlite:///{db}",
            "--email",
            admin_email,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
    assert "FAIL" in result.stderr


def test_check_admin_seed_fail_missing_admin_role(tmp_path: Path) -> None:
    """Test check_admin_seed exits 1 when admin role doesn't exist."""
    db = tmp_path / "fleet.db"
    admin_email = "no-admin-role@example.test"

    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # Insert user and binding but no admin role
        user_id = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO users (id, email, kind, disabled) VALUES (:id, :email, :kind, 0)"
            ),
            {"id": user_id, "email": admin_email, "kind": "local"},
        )

        # Insert a non-admin role for the binding
        role_id = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO roles (id, name, built_in, permissions) VALUES (:id, :name, 1, '[]')"
            ),
            {"id": role_id, "name": "viewer"},
        )

        binding_id = str(uuid4())
        conn.execute(
            text(
                """
                INSERT INTO bindings
                  (id, principal_type, principal_id, role_id, scope_kind, scope_value, scope_hash)
                VALUES (:id, :ptype, :pid, :rid, :kind, :value, :sh)
                """
            ),
            {
                "id": binding_id,
                "ptype": "user",
                "pid": user_id,
                "rid": role_id,
                "kind": "global",
                "value": json.dumps({}),
                "sh": "abc123",
            },
        )

    engine.dispose()

    # Run the helper script - should fail because no admin binding exists
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.tests._helpers.check_admin_seed",
            "--db-url",
            f"sqlite:///{db}",
            "--email",
            admin_email,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
    assert "FAIL" in result.stderr
