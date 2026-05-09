"""roles and bindings

Revision ID: 0005_roles
Revises: 0004_users
Create Date: 2026-05-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4
import json

import sqlalchemy as sa
from alembic import op

revision: str = "0005_roles"
down_revision: Union[str, None] = "0004_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All permissions in the system (used for role seed data)
_ALL_PERMISSIONS = (
    "host:read", "host:write", "host:exec", "host:reboot", "host:shutdown", "host:enroll", "host:revoke",
    "host:terminal", "host:file_transfer", "group:read", "group:write", "group:assign", "task:read",
    "task:create", "task:cancel", "task:approve", "update:read", "update:trigger", "update:approve",
    "update:policy_write", "container:read", "container:update", "container:exec",
    "container:policy_write", "container:registry_write", "secret:read", "secret:write",
    "secret:rotate", "plugin:read", "plugin:install", "plugin:configure", "plugin:invoke", "user:read",
    "user:write", "user:impersonate", "role:read", "role:write", "audit:read", "audit:export",
    "audit:verify", "setting:read", "setting:write", "notification:read", "notification:write",
    "notification:test", "webhook:read", "webhook:write", "webhook:trigger", "power:wol",
    "power:event_subscribe", "session:read", "session:terminate", "session:record_view",
    "integration:read", "integration:write", "events:subscribe", "docs:read"
)


def seed_builtin_roles(connection):
    """Seed the four built-in roles into the roles table."""
    # Compute permission sets for each role
    viewer_perms = [p for p in _ALL_PERMISSIONS if p.endswith(":read")]

    operator_perms = set(viewer_perms) | {
        "host:exec", "host:terminal", "host:file_transfer",
        "task:create", "task:cancel", "update:trigger", "container:update",
        "events:subscribe", "audit:read"
    }

    admin_perms = set(_ALL_PERMISSIONS) - {"user:impersonate"}

    owner_perms = set(_ALL_PERMISSIONS)

    # Build role rows
    roles = [
        {
            "id": str(uuid4()),
            "name": "viewer",
            "description": "View-only access",
            "built_in": True,
            "permissions": json.dumps(sorted(viewer_perms)),
        },
        {
            "id": str(uuid4()),
            "name": "operator",
            "description": "Operator with task and container management",
            "built_in": True,
            "permissions": json.dumps(sorted(operator_perms)),
        },
        {
            "id": str(uuid4()),
            "name": "admin",
            "description": "Administrator without user impersonation",
            "built_in": True,
            "permissions": json.dumps(sorted(admin_perms)),
        },
        {
            "id": str(uuid4()),
            "name": "owner",
            "description": "Full control including user impersonation",
            "built_in": True,
            "permissions": json.dumps(sorted(owner_perms)),
        },
    ]

    # Insert roles
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("built_in", sa.Boolean),
        sa.column("permissions", sa.JSON),
    )

    for role in roles:
        connection.execute(roles_table.insert().values(**role))


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_role_name"),
    )
    op.create_table(
        "bindings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("principal_type", sa.Enum("user", "user_group", "service_account", name="principaltype"), nullable=False),
        sa.Column("principal_id", sa.String(36), nullable=False),
        sa.Column("role_id", sa.String(36), nullable=False),
        sa.Column("scope_kind", sa.Enum("global", "group", "tag", "host_list", "self", name="scopekind"), nullable=False),
        sa.Column("scope_value", sa.JSON(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("principal_type", "principal_id", "role_id", "scope_hash", name="uq_binding_principal_role_scope"),
    )

    # Seed the built-in roles
    seed_builtin_roles(op.get_context().connection)


def downgrade() -> None:
    op.drop_table("bindings")
    op.drop_table("roles")
