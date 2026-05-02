"""Tests for built-in role permission constants."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from server.app.models import Role
from server.app.rbac.roles import BUILTIN_ROLES, VIEWER_PERMS, OPERATOR_PERMS, ADMIN_PERMS, OWNER_PERMS


def test_viewer_operator_admin_owner_hierarchy() -> None:
    """Test that viewer ⊆ operator ⊆ admin ⊆ owner."""
    assert VIEWER_PERMS <= OPERATOR_PERMS
    assert OPERATOR_PERMS <= ADMIN_PERMS
    assert ADMIN_PERMS <= OWNER_PERMS


def test_user_impersonate_in_owner_not_admin() -> None:
    """Test that user:impersonate is in OWNER_PERMS but not ADMIN_PERMS."""
    assert "user:impersonate" in OWNER_PERMS
    assert "user:impersonate" not in ADMIN_PERMS


def test_operator_contains_viewer_perms_plus_extras() -> None:
    """Test that OPERATOR_PERMS contains all viewer perms plus named extras."""
    expected_extras = {
        "host:exec", "host:terminal", "host:file_transfer",
        "task:create", "task:cancel", "update:trigger",
        "container:update", "events:subscribe", "audit:read",
    }
    assert VIEWER_PERMS <= OPERATOR_PERMS
    assert expected_extras <= OPERATOR_PERMS


def test_builtin_roles_dict_matches_constants() -> None:
    """Test that BUILTIN_ROLES dict has the right structure."""
    assert "viewer" in BUILTIN_ROLES
    assert "operator" in BUILTIN_ROLES
    assert "admin" in BUILTIN_ROLES
    assert "owner" in BUILTIN_ROLES

    assert BUILTIN_ROLES["viewer"] == VIEWER_PERMS
    assert BUILTIN_ROLES["operator"] == OPERATOR_PERMS
    assert BUILTIN_ROLES["admin"] == ADMIN_PERMS
    assert BUILTIN_ROLES["owner"] == OWNER_PERMS


@pytest.mark.asyncio
async def test_builtin_roles_sync_with_database(sm) -> None:
    """Verify built-in roles in DB match BUILTIN_ROLES constants."""
    async with sm() as session:
        rows = (await session.execute(
            select(Role).where(Role.built_in).order_by(Role.name)
        )).scalars().all()

        db_roles = {r.name: set(r.permissions or []) for r in rows}

        # Verify all built-in roles exist in DB
        for name, expected_perms in BUILTIN_ROLES.items():
            assert name in db_roles, f"Role {name} not found in database"
            actual_perms = db_roles[name]
            assert actual_perms == expected_perms, (
                f"Role {name} permissions mismatch. "
                f"Expected {expected_perms}, got {actual_perms}"
            )
