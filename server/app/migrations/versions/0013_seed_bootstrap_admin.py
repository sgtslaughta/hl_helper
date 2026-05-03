"""Seed bootstrap admin binding for production deployments.

Revision ID: 0013_seed_bootstrap_admin
Revises: 0012_command_idempotency_key
Create Date: 2026-05-03 14:00:00.000000

"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0013_seed_bootstrap_admin"
down_revision: Union[str, None] = "0012_command_idempotency_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _compute_scope_hash(kind: str, value: dict[str, object]) -> str:
    """Compute scope_hash from kind and value (must match production helper)."""
    canon = json.dumps({"kind": kind, "value": value}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def upgrade() -> None:
    """Seed bootstrap admin if FLEET_BOOTSTRAP_ADMIN_EMAIL is set."""
    admin_email = os.environ.get("FLEET_BOOTSTRAP_ADMIN_EMAIL")

    if not admin_email:
        # No-op: production must opt in
        return

    connection = op.get_context().connection

    # Look up admin role
    admin_role_result = connection.execute(
        sa.text("SELECT id FROM roles WHERE name = 'admin'")
    )
    admin_role_id = admin_role_result.scalar()
    if not admin_role_id:
        raise RuntimeError("Built-in 'admin' role not found — prior migration must create it")

    # Check if user already exists
    user_result = connection.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": admin_email},
    )
    user_id = user_result.scalar()

    # If not, insert user. Do NOT call connection.commit() — alembic owns the
    # transaction; an explicit commit here breaks alembic_version tracking
    # across upgrade/downgrade cycles.
    if not user_id:
        user_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO users (id, email, kind) VALUES (:id, :email, :kind)"
            ),
            {
                "id": user_id,
                "email": admin_email,
                "kind": "local",
            },
        )

    # Compute scope_hash for global scope
    scope_hash = _compute_scope_hash("global", {})

    # Check if binding already exists
    binding_result = connection.execute(
        sa.text(
            """
            SELECT id FROM bindings
            WHERE principal_type = :ptype AND principal_id = :pid
              AND role_id = :rid AND scope_hash = :sh
            """
        ),
        {
            "ptype": "user",
            "pid": user_id,
            "rid": admin_role_id,
            "sh": scope_hash,
        },
    )
    if binding_result.scalar():
        # Already exists, idempotent
        return

    # Insert binding
    binding_id = str(uuid4())
    connection.execute(
        sa.text(
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


def downgrade() -> None:
    """Remove bootstrap admin if FLEET_BOOTSTRAP_ADMIN_EMAIL is set.

    DESTRUCTIVE: deletes the seeded user and ALL their bindings. If an operator added
    additional bindings via API after upgrade, those are lost. Recommended: snapshot the
    user's bindings before downgrade, or skip downgrade and manage admin removal via the
    API instead.
    """
    admin_email = os.environ.get("FLEET_BOOTSTRAP_ADMIN_EMAIL")

    if not admin_email:
        # No-op
        return

    connection = op.get_context().connection

    # Find user by email
    user_result = connection.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": admin_email},
    )
    user_id = user_result.scalar()

    if not user_id:
        # User doesn't exist, nothing to do
        return

    # Delete bindings for this user
    connection.execute(
        sa.text("DELETE FROM bindings WHERE principal_id = :uid"),
        {"uid": user_id},
    )

    # Delete user
    connection.execute(
        sa.text("DELETE FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
