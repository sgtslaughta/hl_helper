"""add plugin:enable + plugin:manage to admin/owner roles

Revision ID: 0023_plugin_role_perms
Revises: 0022_plugins
Create Date: 2026-05-04 19:55:00.000000

"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_plugin_role_perms"
down_revision: Union[str, None] = "0022_plugins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMS = ("plugin:enable", "plugin:manage")
_TARGET_ROLES = ("admin", "owner")


def _get_perms(connection, role_name: str) -> list[str]:
    row = connection.execute(
        sa.text("SELECT permissions FROM roles WHERE name = :n"),
        {"n": role_name},
    ).fetchone()
    if row is None:
        return []
    raw = row[0]
    if isinstance(raw, str):
        return list(json.loads(raw))
    return list(raw or [])


def _set_perms(connection, role_name: str, perms: list[str]) -> None:
    connection.execute(
        sa.text("UPDATE roles SET permissions = :p WHERE name = :n"),
        {"p": json.dumps(sorted(perms)), "n": role_name},
    )


def upgrade() -> None:
    conn = op.get_bind()
    for role_name in _TARGET_ROLES:
        perms = set(_get_perms(conn, role_name))
        perms.update(_NEW_PERMS)
        _set_perms(conn, role_name, sorted(perms))


def downgrade() -> None:
    conn = op.get_bind()
    for role_name in _TARGET_ROLES:
        perms = set(_get_perms(conn, role_name))
        perms.difference_update(_NEW_PERMS)
        _set_perms(conn, role_name, sorted(perms))
