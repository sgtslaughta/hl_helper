"""Test helper for seeding RBAC bindings with real provider support.

Provides async functions to create users and bind them to roles with specific scopes,
enabling tests to validate RBAC decisions without requiring permissive stubs.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.bindings import _compute_scope_hash
from server.app.models import Binding, Role, User
from server.app.models.binding import PrincipalType, ScopeKind


async def grant_admin(session: AsyncSession, *, user_id: str) -> str:
    """Bind user to the built-in 'admin' role with global scope.

    Returns the new Binding id.
    Inserts the user_id row if missing (kind='local'), inserts admin role
    membership.

    Args:
        session: AsyncSession for database access
        user_id: Unique identifier for the user

    Returns:
        Binding.id of the created/existing binding

    Raises:
        ValueError: If the admin role is not found
    """
    # Look up admin role
    role = await session.scalar(select(Role).where(Role.name == "admin"))
    if not role:
        raise ValueError("Role 'admin' not found")

    # Look up or create user
    user = await session.scalar(select(User).where(User.id == user_id))
    if not user:
        user = User(id=user_id, email=f"{user_id}@test.local", kind="local")
        session.add(user)
        await session.flush()

    # Pre-check for idempotency (avoid IntegrityError on aiosqlite).
    scope_kind = "global"
    scope_value: dict[str, object] = {}
    scope_hash = _compute_scope_hash(scope_kind, scope_value)

    existing = await session.scalar(
        select(Binding).where(
            (Binding.principal_type == PrincipalType.USER)
            & (Binding.principal_id == user_id)
            & (Binding.role_id == role.id)
            & (Binding.scope_hash == scope_hash)
        )
    )
    if existing is not None:
        return str(existing.id)

    binding = Binding(
        principal_type=PrincipalType.USER,
        principal_id=user_id,
        role_id=role.id,
        scope_kind=ScopeKind.GLOBAL,
        scope_value=scope_value,
        scope_hash=scope_hash,
    )
    session.add(binding)
    await session.commit()
    await session.refresh(binding)
    return str(binding.id)


async def grant_role_on_group(
    session: AsyncSession, *, user_id: str, role_name: str, group_id: str
) -> str:
    """Bind user → role → group scope. Computes scope_hash deterministically.

    Args:
        session: AsyncSession for database access
        user_id: Unique identifier for the user
        role_name: Name of the role to grant (e.g., "operator", "viewer")
        group_id: The group_id scope value

    Returns:
        Binding.id of the created/existing binding

    Raises:
        ValueError: If the role is not found
    """
    # Look up role by name
    role = await session.scalar(select(Role).where(Role.name == role_name))
    if not role:
        raise ValueError(f"Role '{role_name}' not found")

    # Look up or create user
    user = await session.scalar(select(User).where(User.id == user_id))
    if not user:
        user = User(id=user_id, email=f"{user_id}@test.local", kind="local")
        session.add(user)
        await session.flush()

    # Create binding with group scope. Pre-check for an existing binding to
    # support idempotent grants without relying on IntegrityError rollback —
    # the latter triggers MissingGreenlet on aiosqlite when reused on the
    # same session after a failed flush.
    scope_kind = "group"
    scope_value: dict[str, object] = {"group_id": group_id}
    scope_hash = _compute_scope_hash(scope_kind, scope_value)

    existing = await session.scalar(
        select(Binding).where(
            (Binding.principal_type == PrincipalType.USER)
            & (Binding.principal_id == user_id)
            & (Binding.role_id == role.id)
            & (Binding.scope_hash == scope_hash)
        )
    )
    if existing is not None:
        return str(existing.id)

    binding = Binding(
        principal_type=PrincipalType.USER,
        principal_id=user_id,
        role_id=role.id,
        scope_kind=ScopeKind.GROUP,
        scope_value=scope_value,
        scope_hash=scope_hash,
    )
    session.add(binding)
    await session.commit()
    await session.refresh(binding)
    return str(binding.id)


async def grant_role_on_host_list(
    session: AsyncSession, *, user_id: str, role_name: str, host_ids: list[str]
) -> str:
    """Bind user → role → host_list scope.

    Args:
        session: AsyncSession for database access
        user_id: Unique identifier for the user
        role_name: Name of the role to grant (e.g., "operator", "viewer")
        host_ids: List of host IDs to grant access to

    Returns:
        Binding.id of the created/existing binding

    Raises:
        ValueError: If the role is not found
    """
    # Look up role by name
    role = await session.scalar(select(Role).where(Role.name == role_name))
    if not role:
        raise ValueError(f"Role '{role_name}' not found")

    # Look up or create user
    user = await session.scalar(select(User).where(User.id == user_id))
    if not user:
        user = User(id=user_id, email=f"{user_id}@test.local", kind="local")
        session.add(user)
        await session.flush()

    # Pre-check for idempotency (avoid IntegrityError on aiosqlite).
    scope_kind = "host_list"
    scope_value: dict[str, object] = {"host_ids": host_ids}
    scope_hash = _compute_scope_hash(scope_kind, scope_value)

    existing = await session.scalar(
        select(Binding).where(
            (Binding.principal_type == PrincipalType.USER)
            & (Binding.principal_id == user_id)
            & (Binding.role_id == role.id)
            & (Binding.scope_hash == scope_hash)
        )
    )
    if existing is not None:
        return str(existing.id)

    binding = Binding(
        principal_type=PrincipalType.USER,
        principal_id=user_id,
        role_id=role.id,
        scope_kind=ScopeKind.HOST_LIST,
        scope_value=scope_value,
        scope_hash=scope_hash,
    )
    session.add(binding)
    await session.commit()
    await session.refresh(binding)
    return str(binding.id)
