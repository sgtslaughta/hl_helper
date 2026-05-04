"""Tests for per-component posture finding modules added in C12 Phase 4.2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from server.app.models import Approval, Binding, Host, Role, User
from server.app.models.binding import PrincipalType, ScopeKind
from server.app.models.user import UserKind
from server.app.posture import (
    ALL_FINDINGS,
    findings_docker as fd,
    findings_packaging as fp,
    findings_plugins as fpl,
    findings_rbac as frbac,
    findings_terminal as fterm,
    findings_transport as ftrans,
    findings_update as fupd,
)


# ---------- transport (C1) ----------


@pytest.mark.asyncio
async def test_hosts_unreachable_no_findings_when_seen(sm) -> None:
    async with sm() as s:
        s.add(
            Host(
                id="h-1",
                hostname="h1",
                agent_pubkey=b"\x00" * 32,
                last_seen_at=datetime.now(timezone.utc),
            )
        )
        await s.commit()
    assert await ftrans.hosts_unreachable_recently(sm) is None


@pytest.mark.asyncio
async def test_hosts_unreachable_flags_when_never_seen(sm) -> None:
    async with sm() as s:
        s.add(Host(id="h-2", hostname="h2", agent_pubkey=b"\x00" * 32, last_seen_at=None))
        await s.commit()
    f = await ftrans.hosts_unreachable_recently(sm)
    assert f is not None
    assert f.severity == "medium"
    assert f.id == "hosts_never_checked_in"


@pytest.mark.asyncio
async def test_hosts_with_expired_certs_flags(sm) -> None:
    expired = datetime.now(timezone.utc) - timedelta(days=2)
    async with sm() as s:
        s.add(
            Host(
                id="h-3",
                hostname="h3",
                agent_pubkey=b"\x00" * 32,
                cert_expires_at=expired,
            )
        )
        await s.commit()
    f = await ftrans.hosts_with_expired_certs(sm)
    assert f is not None
    assert f.severity == "high"


# ---------- rbac (C2) ----------


@pytest.mark.asyncio
async def test_no_owner_account_flags_when_no_binding(sm) -> None:
    # No owner role + no binding -> finding fires
    f = await frbac.no_owner_account(sm)
    assert f is not None
    assert f.severity == "critical"


@pytest.mark.asyncio
async def test_no_owner_account_clears_when_bound(sm) -> None:
    owner_role_id = str(uuid4())
    async with sm() as s:
        s.add(Role(id=owner_role_id, name="owner", built_in=True, permissions=["*"]))
        s.add(User(id="u-own", email="o@x", kind=UserKind.LOCAL))
        await s.commit()
        s.add(
            Binding(
                id=str(uuid4()),
                principal_type=PrincipalType.USER,
                principal_id="u-own",
                role_id=owner_role_id,
                scope_kind=ScopeKind.GLOBAL,
                scope_value={},
                scope_hash="x" * 64,
            )
        )
        await s.commit()
    assert await frbac.no_owner_account(sm) is None


@pytest.mark.asyncio
async def test_stale_pending_approvals_flags(sm) -> None:
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    async with sm() as s:
        s.add(
            Approval(
                id="a-stale",
                subject_type="command",
                subject_id="c-1",
                policy="single",
                requester_id="u-r",
                state="pending",
                expires_at=past,
            )
        )
        await s.commit()
    f = await frbac.stale_pending_approvals(sm)
    assert f is not None
    assert f.severity == "medium"


# ---------- update (C4) ----------


@pytest.mark.asyncio
async def test_update_engine_not_configured_flags(sm) -> None:
    f = await fupd.update_engine_not_configured(sm)
    assert f is not None
    assert f.severity == "info"


# ---------- docker (C7) ----------


@pytest.mark.asyncio
async def test_docker_not_implemented_always_info(sm) -> None:
    f = await fd.docker_management_not_implemented(sm)
    assert f is not None
    assert f.severity == "info"


# ---------- plugins (C6) ----------


@pytest.mark.asyncio
async def test_plugin_stub_only(sm) -> None:
    f = await fpl.plugin_system_stub_only(sm)
    assert f is not None
    assert f.severity == "info"


# ---------- terminal (C9) ----------


@pytest.mark.asyncio
async def test_terminal_not_implemented(sm) -> None:
    f = await fterm.terminal_not_implemented(sm)
    assert f is not None
    assert f.severity == "info"


# ---------- packaging (C11) ----------


@pytest.mark.asyncio
async def test_install_script_template_present(sm) -> None:
    # repo ships the template; finding should not fire
    assert await fp.install_script_template_missing(sm) is None


# ---------- registry ----------


def test_all_findings_registry_includes_new_modules() -> None:
    names = {fn.__name__ for fn in ALL_FINDINGS}
    expected = {
        "hosts_unreachable_recently",
        "hosts_with_expired_certs",
        "no_owner_account",
        "stale_pending_approvals",
        "excessive_admin_count",
        "update_engine_not_configured",
        "docker_management_not_implemented",
        "plugin_system_stub_only",
        "terminal_not_implemented",
        "install_script_template_missing",
        "release_signing_not_configured",
    }
    assert expected.issubset(names)
