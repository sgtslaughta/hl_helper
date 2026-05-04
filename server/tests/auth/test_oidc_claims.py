"""Tests for OIDC claim mapping + JIT provisioning (Phase 4.3)."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from server.app.auth.oidc.claims import (
    MappedClaims,
    OidcLinkError,
    apply_claim_mappings,
    jit_provision,
    link_account,
)
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import Base, OidcAccountLink, OidcProvider, Role, User
from server.app.models.binding import Binding, PrincipalType, ScopeKind
from server.app.models.user import UserKind


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """Fresh in-memory SQLite engine with all tables created."""
    eng = make_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sm(engine: AsyncEngine) -> async_sessionmaker:
    return make_sessionmaker(engine)


@pytest_asyncio.fixture
async def provider(sm: async_sessionmaker) -> OidcProvider:
    p = OidcProvider(
        name="test-idp",
        issuer="https://idp.example",
        client_id="cid",
        scopes=["openid", "email", "profile"],
        claim_mappings={"email": "email", "display_name": "name", "groups": "groups"},
    )
    async with sm() as s:
        s.add(p)
        await s.commit()
        await s.refresh(p)
    return p


# --------------------------------------------------------------------------- #
# apply_claim_mappings
# --------------------------------------------------------------------------- #


def test_apply_simple_mapping() -> None:
    claims = {"email": "u@x", "name": "U", "groups": ["g1", "g2"]}
    out = apply_claim_mappings(claims, {"email": "email", "display_name": "name", "groups": "groups"})
    assert out.email == "u@x"
    assert out.display_name == "U"
    assert out.groups == ["g1", "g2"]


def test_apply_nested_jsonpath() -> None:
    claims = {"email": "u@x", "realm_access": {"roles": ["admin", "viewer"]}}
    out = apply_claim_mappings(
        claims, {"email": "email", "display_name": "preferred_username", "groups": "realm_access.roles"}
    )
    assert out.groups == ["admin", "viewer"]


def test_apply_multiple_group_paths_union() -> None:
    claims = {"email": "u@x", "groups": ["g1"], "roles": ["g2", "g1"]}
    out = apply_claim_mappings(
        claims, {"email": "email", "display_name": "name", "groups": ["groups", "roles"]}
    )
    # Union dedup, order preserved
    assert out.groups == ["g1", "g2"]


def test_apply_missing_path_returns_none() -> None:
    claims = {"email": "u@x"}
    out = apply_claim_mappings(claims, {"email": "email", "display_name": "missing.path", "groups": "missing.groups"})
    assert out.display_name is None
    assert out.groups == []


def test_apply_dollar_prefix_stripped() -> None:
    claims = {"a": {"b": "v"}}
    out = apply_claim_mappings(claims, {"email": "$.a.b", "display_name": "name", "groups": []})
    assert out.email == "v"


def test_apply_string_group_value() -> None:
    """If the claim is a single string, treat as one-element list."""
    claims = {"email": "u@x", "groups": "the-group"}
    out = apply_claim_mappings(claims, {"email": "email", "display_name": "name", "groups": "groups"})
    assert out.groups == ["the-group"]


# --------------------------------------------------------------------------- #
# jit_provision
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_jit_creates_user_and_link(sm: async_sessionmaker, provider: OidcProvider) -> None:
    claims = {"sub": "sub-1", "email": "alice@x", "name": "Alice"}
    mapped = apply_claim_mappings(claims, provider.claim_mappings)
    user = await jit_provision(sm, provider, claims, mapped)
    assert user.email == "alice@x"
    assert user.kind == UserKind.OIDC
    async with sm() as s:
        link = await s.scalar(
            select(OidcAccountLink).where(
                OidcAccountLink.provider_id == provider.id,
                OidcAccountLink.subject == "sub-1",
            )
        )
        assert link is not None
        assert link.user_id == user.id


@pytest.mark.asyncio
async def test_jit_idempotent_same_sub(sm: async_sessionmaker, provider: OidcProvider) -> None:
    claims = {"sub": "sub-2", "email": "bob@x", "name": "Bob"}
    mapped = apply_claim_mappings(claims, provider.claim_mappings)
    u1 = await jit_provision(sm, provider, claims, mapped)
    u2 = await jit_provision(sm, provider, claims, mapped)
    assert u1.id == u2.id
    async with sm() as s:
        links = (await s.execute(select(OidcAccountLink).where(OidcAccountLink.subject == "sub-2"))).scalars().all()
        assert len(links) == 1


@pytest.mark.asyncio
async def test_jit_existing_user_linked(sm: async_sessionmaker, provider: OidcProvider) -> None:
    """If user already exists by email AND IdP asserts email_verified, link instead of new user."""
    pre = User(id=str(uuid4()), email="carol@x", kind=UserKind.LOCAL, password_hash="pw")
    async with sm() as s:
        s.add(pre)
        await s.commit()
    claims = {"sub": "sub-3", "email": "carol@x", "name": "Carol", "email_verified": True}
    mapped = apply_claim_mappings(claims, provider.claim_mappings)
    u = await jit_provision(sm, provider, claims, mapped)
    assert u.id == pre.id
    async with sm() as s:
        link = await s.scalar(select(OidcAccountLink).where(OidcAccountLink.subject == "sub-3"))
        assert link is not None and link.user_id == pre.id


@pytest.mark.asyncio
async def test_jit_existing_user_unverified_email_rejected(
    sm: async_sessionmaker, provider: OidcProvider
) -> None:
    """If user exists by email but IdP did NOT assert email_verified, reject."""
    pre = User(id=str(uuid4()), email="mallory@x", kind=UserKind.LOCAL, password_hash="pw")
    async with sm() as s:
        s.add(pre)
        await s.commit()
    claims = {"sub": "attacker-sub", "email": "mallory@x", "name": "Mallory"}
    mapped = apply_claim_mappings(claims, provider.claim_mappings)
    with pytest.raises(OidcLinkError, match="email_not_verified"):
        await jit_provision(sm, provider, claims, mapped)


@pytest.mark.asyncio
async def test_jit_group_binding_best_effort(sm: async_sessionmaker, provider: OidcProvider) -> None:
    # Seed a role named like an expected group
    role = Role(id=str(uuid4()), name="viewer", description="d", built_in=True, permissions=[])
    async with sm() as s:
        s.add(role)
        await s.commit()
    claims = {"sub": "sub-4", "email": "dan@x", "name": "Dan", "groups": ["viewer", "unknown-grp"]}
    mapped = apply_claim_mappings(claims, provider.claim_mappings)
    user = await jit_provision(sm, provider, claims, mapped)
    async with sm() as s:
        bindings = (
            await s.execute(
                select(Binding).where(
                    Binding.principal_id == user.id,
                    Binding.principal_type == PrincipalType.USER,
                )
            )
        ).scalars().all()
        assert len(bindings) == 1  # only the known role
        assert bindings[0].role_id == role.id
        assert bindings[0].scope_kind == ScopeKind.GLOBAL


@pytest.mark.asyncio
async def test_jit_missing_email_raises(sm: async_sessionmaker, provider: OidcProvider) -> None:
    claims = {"sub": "sub-5"}
    mapped = MappedClaims(email=None, display_name=None, groups=[])
    with pytest.raises(OidcLinkError, match="missing_email"):
        await jit_provision(sm, provider, claims, mapped)


@pytest.mark.asyncio
async def test_jit_missing_sub_raises(sm: async_sessionmaker, provider: OidcProvider) -> None:
    claims = {"email": "x@y"}
    mapped = MappedClaims(email="x@y", display_name=None, groups=[])
    with pytest.raises(OidcLinkError, match="missing_sub"):
        await jit_provision(sm, provider, claims, mapped)


# --------------------------------------------------------------------------- #
# link_account
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_link_account_happy(sm: async_sessionmaker, provider: OidcProvider) -> None:
    user = User(id=str(uuid4()), email="eve@x", kind=UserKind.LOCAL, password_hash="pw")
    async with sm() as s:
        s.add(user)
        await s.commit()
    link = await link_account(sm, user, provider, subject="ext-sub-1", email="eve@x")
    assert link.user_id == user.id
    assert link.subject == "ext-sub-1"


@pytest.mark.asyncio
async def test_link_account_duplicate_raises(sm: async_sessionmaker, provider: OidcProvider) -> None:
    user = User(id=str(uuid4()), email="frank@x", kind=UserKind.LOCAL, password_hash="pw")
    async with sm() as s:
        s.add(user)
        await s.commit()
    await link_account(sm, user, provider, subject="ext-sub-2", email="frank@x")
    with pytest.raises(OidcLinkError, match="already_linked"):
        await link_account(sm, user, provider, subject="ext-sub-2", email="frank@x")
