"""Fixtures for model tests."""

from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base, Role


# All permissions in the system (mirrors migration constant)
_ALL_PERMISSIONS = (
    "host:read", "host:write", "host:exec", "host:reboot", "host:shutdown", "host:enroll", "host:revoke",
    "host:terminal", "host:file_transfer", "group:read", "group:write", "group:assign", "task:read",
    "task:create", "task:cancel", "task:approve", "update:read", "update:trigger", "update:approve",
    "update:policy_write", "container:read", "container:update", "container:exec",
    "container:policy_write", "container:registry_write", "secret:read", "secret:write",
    "secret:rotate", "plugin:read", "plugin:install", "plugin:enable", "plugin:manage",
    "plugin:configure", "plugin:invoke", "user:read",
    "user:write", "user:impersonate", "role:read", "role:write", "audit:read", "audit:export",
    "audit:verify", "setting:read", "setting:write", "notification:read", "notification:write",
    "notification:test", "webhook:read", "webhook:write", "webhook:trigger", "power:wol",
    "power:event_subscribe", "session:read", "session:terminate", "session:record_view",
    "integration:read", "integration:write", "events:subscribe", "docs:read",
)


async def _seed_builtin_roles(session_maker: async_sessionmaker) -> None:
    """Seed the four built-in roles into the database."""
    # Compute permission sets for each role
    viewer_perms = [p for p in _ALL_PERMISSIONS if p.endswith(":read")]

    operator_perms = list(set(viewer_perms) | {
        "host:exec", "host:terminal", "host:file_transfer",
        "task:create", "task:cancel", "update:trigger", "container:update",
        "events:subscribe", "audit:read"
    })

    admin_perms = list(set(_ALL_PERMISSIONS) - {"user:impersonate"})

    owner_perms = list(_ALL_PERMISSIONS)

    async with session_maker() as session:
        # Check if roles already exist (idempotent)
        from sqlalchemy import select
        existing = await session.scalar(select(Role).where(Role.name == "viewer"))
        if existing:
            return

        roles = [
            Role(
                id=str(uuid4()),
                name="viewer",
                description="View-only access",
                built_in=True,
                permissions=sorted(viewer_perms),
            ),
            Role(
                id=str(uuid4()),
                name="operator",
                description="Operator with task and container management",
                built_in=True,
                permissions=sorted(operator_perms),
            ),
            Role(
                id=str(uuid4()),
                name="admin",
                description="Administrator without user impersonation",
                built_in=True,
                permissions=sorted(admin_perms),
            ),
            Role(
                id=str(uuid4()),
                name="owner",
                description="Full control including user impersonation",
                built_in=True,
                permissions=sorted(owner_perms),
            ),
        ]
        session.add_all(roles)
        await session.commit()


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """Create an in-memory SQLite engine and initialize all tables."""
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def sm(engine: AsyncEngine) -> async_sessionmaker:
    """Create a sessionmaker for the test engine."""
    session_maker = make_sessionmaker(engine)
    # Seed built-in roles
    await _seed_builtin_roles(session_maker)
    return session_maker
