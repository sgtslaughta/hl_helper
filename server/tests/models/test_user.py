"""Tests for User, UserGroup, ApiKey, and ServiceAccount models."""

from __future__ import annotations

import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models import User, UserGroup, ApiKey, ServiceAccount


@pytest.mark.asyncio
async def test_user_local_kind(sm: async_sessionmaker) -> None:
    """Create a local user with password hash."""
    async with sm() as session:
        u = User(id="u-1", email="a@b.c", kind="local", password_hash="$argon2id$...")
        session.add(u)
        await session.commit()
        got = await session.scalar(select(User).where(User.email == "a@b.c"))
        assert got.kind == "local"
        assert got.password_hash == "$argon2id$..."


@pytest.mark.asyncio
async def test_user_oidc_kind(sm: async_sessionmaker) -> None:
    """Create an OIDC user with subject and issuer."""
    async with sm() as session:
        u = User(
            id="u-2",
            email="x@y.z",
            kind="oidc",
            oidc_subject="sub-123",
            oidc_issuer="https://idp",
        )
        session.add(u)
        await session.commit()
        got = await session.scalar(select(User).where(User.id == "u-2"))
        assert got.oidc_subject == "sub-123"
        assert got.oidc_issuer == "https://idp"


@pytest.mark.asyncio
async def test_user_group_membership(sm: async_sessionmaker) -> None:
    """Create a user and group, then add membership."""
    async with sm() as session:
        u = User(id="u-3", email="m@m.m", kind="local")
        g = UserGroup(id="ug-1", name="ops")
        session.add_all([u, g])
        await session.commit()

        # Use raw association via the join table
        from server.app.models.user_group import user_group_members

        await session.execute(
            user_group_members.insert().values(user_id="u-3", user_group_id="ug-1")
        )
        await session.commit()

        rows = (await session.execute(select(user_group_members))).all()
        assert ("u-3", "ug-1") in [
            (r.user_id, r.user_group_id) for r in rows
        ]


@pytest.mark.asyncio
async def test_api_key_hash_storage(sm: async_sessionmaker) -> None:
    """Create an API key with hash storage (no plaintext)."""
    async with sm() as session:
        sa = ServiceAccount(id="sa-1", name="ci-runner")
        session.add(sa)
        await session.commit()

        plaintext = "hlk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # 36 chars
        h = hashlib.sha256(plaintext.encode()).digest()
        k = ApiKey(
            id="k-1",
            prefix=plaintext[:8],
            last_4=plaintext[-4:],
            key_hash=h,
            principal_id="sa-1",
            principal_kind="service_account",
            name="ci",
        )
        session.add(k)
        await session.commit()

        got = await session.scalar(select(ApiKey).where(ApiKey.id == "k-1"))
        assert got.key_hash == h
        assert got.prefix == "hlk_AAAA"
        assert got.last_4 == "AAAA"
        # Plaintext must not be stored anywhere
        assert plaintext not in got.prefix
        assert plaintext not in got.last_4
