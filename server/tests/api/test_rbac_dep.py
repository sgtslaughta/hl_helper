"""Tests for FastAPI RBAC dependency factory (require)."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.signing import FileBackend
from server.app.deps import current_principal
from server.app.deps_rbac import require
from server.app.models import AuditEntry, Binding, Role
from server.app.rbac import Principal, Resource
from server.tests._helpers.app_state import make_test_app_state


@pytest.mark.asyncio
async def test_require_returns_401_without_principal():
    """No principal in request → 401 problem+JSON."""
    app = FastAPI()

    @app.get("/p", dependencies=[Depends(require("host:read"))])
    async def p() -> dict:
        return {}

    with TestClient(app) as c:
        r = c.get("/p")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_require_grants_when_principal_authorized(
    sm: async_sessionmaker,
    signing_backend: FileBackend,
) -> None:
    """Principal with operator role on global scope → 200."""
    # Seed a role + binding for the principal
    async with sm() as session:
        role = Role(
            id="r-op",
            name="op-test",
            built_in=False,
            permissions=["host:read"],
        )
        session.add(role)
        await session.flush()
        scope_value = {}
        scope_hash = hashlib.sha256(
            json.dumps(
                {"kind": "global", "value": {}}, sort_keys=True
            ).encode()
        ).hexdigest()
        b = Binding(
            id="b-1",
            principal_type="user",
            principal_id="u-1",
            role_id="r-op",
            scope_kind="global",
            scope_value=scope_value,
            scope_hash=scope_hash,
        )
        session.add(b)
        await session.commit()

    app = FastAPI()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    fake_principal = Principal(user_id="u-1")
    app.dependency_overrides[current_principal] = lambda: fake_principal

    @app.get("/p", dependencies=[Depends(require("host:read"))])
    async def p() -> dict:
        return {"ok": True}

    with TestClient(app) as c:
        r = c.get("/p")
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_require_emits_audit_on_deny(
    sm: async_sessionmaker,
    signing_backend: FileBackend,
) -> None:
    """Authorized principal but missing perm → 403 + audit entry."""
    audit = SqlAuditChain(signing_backend)

    app = FastAPI()
    app.state.app_state = make_test_app_state(sessionmaker=sm, audit_chain=audit)

    fake_principal = Principal(user_id="u-deny")
    app.dependency_overrides[current_principal] = lambda: fake_principal

    @app.get("/blocked", dependencies=[Depends(require("host:exec"))])
    async def b() -> dict:
        return {}

    with TestClient(app) as c:
        r = c.get("/blocked")
        assert r.status_code == 403

    async with sm() as session:
        rows = (await session.execute(select(AuditEntry))).scalars().all()
        actions = [r.action for r in rows]
        assert any("rbac.denied" in a for a in actions), f"missing rbac.denied; got {actions}"


@pytest.mark.asyncio
async def test_require_with_resource_loader_async(
    sm: async_sessionmaker,
    signing_backend: FileBackend,
) -> None:
    """resource_loader can be async; loaded resource flows into authz."""
    app = FastAPI()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="u-x")

    async def load_host(req) -> Resource:
        return Resource(id="h-42", group_ids=frozenset({"g-prod"}))

    @app.get("/h/{host_id}", dependencies=[Depends(require("host:read", load_host))])
    async def h(host_id: str) -> dict:
        return {"id": host_id}

    with TestClient(app) as c:
        r = c.get("/h/h-42")
        # No binding for u-x → 403, but the resource loader path was exercised.
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_require_with_sync_resource_loader(sm: async_sessionmaker) -> None:
    """resource_loader can be a plain sync function."""
    app = FastAPI()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="u-x")

    def load_host(req) -> Resource:
        return Resource(id="h-99")

    @app.get("/h/{host_id}", dependencies=[Depends(require("host:read", load_host))])
    async def h(host_id: str) -> dict:
        return {"id": host_id}

    with TestClient(app) as c:
        r = c.get("/h/h-99")
        # No binding for u-x → 403, but the sync loader path was exercised without TypeError
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_require_returns_decision_with_binding_id(sm: async_sessionmaker) -> None:
    """On grant, dependency value is the Decision with binding_id populated."""
    async with sm() as session:
        role = Role(id="r-bp", name="binding-test", built_in=False, permissions=["host:read"])
        session.add(role)
        await session.flush()
        scope_hash = hashlib.sha256(
            json.dumps({"kind": "global", "value": {}}, sort_keys=True).encode()
        ).hexdigest()
        b = Binding(
            id="b-bp",
            principal_type="user",
            principal_id="u-bp",
            role_id="r-bp",
            scope_kind="global",
            scope_value={},
            scope_hash=scope_hash,
        )
        session.add(b)
        await session.commit()

    app = FastAPI()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="u-bp")

    @app.get("/p")
    async def p(decision=Depends(require("host:read"))) -> dict:
        return {"binding_id": decision.binding_id}

    with TestClient(app) as c:
        r = c.get("/p")
        assert r.status_code == 200
        assert r.json()["binding_id"] == "b-bp"


@pytest.mark.asyncio
async def test_require_audit_payload_contains_perm_and_reason(
    sm: async_sessionmaker,
    signing_backend: FileBackend,
) -> None:
    """Audit payload contains perm and reason on deny."""
    audit = SqlAuditChain(signing_backend)

    app = FastAPI()
    app.state.app_state = make_test_app_state(sessionmaker=sm, audit_chain=audit)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="u-pr")

    @app.get("/blk", dependencies=[Depends(require("host:exec"))])
    async def blk() -> dict:
        return {}

    with TestClient(app) as c:
        c.get("/blk")

    async with sm() as session:
        rows = (await session.execute(select(AuditEntry))).scalars().all()
        deny_rows = [r for r in rows if r.action == "rbac.denied"]
        assert deny_rows, "expected at least one rbac.denied entry"
        payload = deny_rows[0].payload
        assert payload.get("perm") == "host:exec"
        assert "reason" in payload
