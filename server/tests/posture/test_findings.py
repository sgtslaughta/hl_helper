"""Tests for posture findings module (Task 6.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from unittest import mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.api.app import create_app
from server.app.models import Role, Binding, User
from server.app.models.binding import PrincipalType, ScopeKind
from server.app.models.recovery_code import RecoveryCode
from server.app.models.user import UserKind
from server.app.models.webauthn_credential import WebAuthnCredential
from server.app.posture import Finding, ALL_FINDINGS
from server.app.posture import findings_auth_secrets as F
from server.app.settings.config import FleetSettings
from server.tests._helpers.app_state import make_test_app_state


ADMIN_TOKEN = "test-admin-tok-posture"


@pytest.fixture(autouse=True)
def _set_admin_env(monkeypatch):
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", ADMIN_TOKEN)
    yield


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture
async def session(sm: async_sessionmaker) -> AsyncIterator[AsyncSession]:
    async with sm() as s:
        yield s


async def _seed_admin_role(session: AsyncSession) -> Role:
    role = Role(id=str(uuid4()), name="admin", built_in=True, permissions=["*"])
    session.add(role)
    await session.commit()
    return role


async def _seed_user(
    session: AsyncSession, *, kind: UserKind = UserKind.LOCAL, email: str | None = None
) -> User:
    u = User(
        id=str(uuid4()),
        email=email or f"{uuid4()}@example.com",
        kind=kind,
    )
    session.add(u)
    await session.commit()
    return u


async def _seed_binding(session: AsyncSession, *, user: User, role: Role) -> Binding:
    b = Binding(
        id=str(uuid4()),
        principal_type=PrincipalType.USER,
        principal_id=user.id,
        role_id=role.id,
        scope_kind=ScopeKind.GLOBAL,
        scope_value={},
        scope_hash="x" * 64,
    )
    session.add(b)
    await session.commit()
    return b


# ---------------------------------------------------------------------------
# local_password_admins_exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_password_admins_exist_finding(sm, session: AsyncSession):
    role = await _seed_admin_role(session)
    user = await _seed_user(session, kind=UserKind.LOCAL)
    await _seed_binding(session, user=user, role=role)

    f = await F.local_password_admins_exist(sm)
    assert f is not None
    assert f.severity == "medium"
    assert f.id == "local_password_admins_exist"


@pytest.mark.asyncio
async def test_local_password_admins_exist_none_when_oidc(sm, session: AsyncSession):
    role = await _seed_admin_role(session)
    user = await _seed_user(session, kind=UserKind.OIDC)
    await _seed_binding(session, user=user, role=role)

    f = await F.local_password_admins_exist(sm)
    assert f is None


# ---------------------------------------------------------------------------
# admin_without_webauthn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_without_webauthn_finding(sm, session: AsyncSession):
    role = await _seed_admin_role(session)
    user = await _seed_user(session)
    await _seed_binding(session, user=user, role=role)

    f = await F.admin_without_webauthn(sm)
    assert f is not None
    assert f.severity == "medium"


@pytest.mark.asyncio
async def test_admin_with_webauthn_no_finding(sm, session: AsyncSession):
    role = await _seed_admin_role(session)
    user = await _seed_user(session)
    await _seed_binding(session, user=user, role=role)
    cred = WebAuthnCredential(
        id=str(uuid4()),
        user_id=user.id,
        credential_id=b"cred1",
        public_key=b"pk",
        sign_count=0,
    )
    session.add(cred)
    await session.commit()

    f = await F.admin_without_webauthn(sm)
    assert f is None


# ---------------------------------------------------------------------------
# recovery_codes_never_viewed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_codes_never_viewed_finding(sm, session: AsyncSession):
    user = await _seed_user(session)
    rc = RecoveryCode(
        id=str(uuid4()),
        user_id=user.id,
        code_hash=b"\x00" * 32,
        viewed_at=None,
    )
    session.add(rc)
    await session.commit()

    f = await F.recovery_codes_never_viewed(sm)
    assert f is not None
    assert f.severity == "low"


@pytest.mark.asyncio
async def test_recovery_codes_viewed_no_finding(sm, session: AsyncSession):
    user = await _seed_user(session)
    rc = RecoveryCode(
        id=str(uuid4()),
        user_id=user.id,
        code_hash=b"\x00" * 32,
        viewed_at=datetime.now(timezone.utc),
    )
    session.add(rc)
    await session.commit()

    f = await F.recovery_codes_never_viewed(sm)
    assert f is None


# ---------------------------------------------------------------------------
# signcount_regression_recent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signcount_regression_recent_finding(sm, session: AsyncSession):
    user = await _seed_user(session)
    cred = WebAuthnCredential(
        id=str(uuid4()),
        user_id=user.id,
        credential_id=b"cred-flag",
        public_key=b"pk",
        sign_count=0,
        flagged_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    session.add(cred)
    await session.commit()

    f = await F.signcount_regression_recent(sm)
    assert f is not None
    assert f.severity == "high"


@pytest.mark.asyncio
async def test_signcount_regression_old_no_finding(sm, session: AsyncSession):
    user = await _seed_user(session)
    cred = WebAuthnCredential(
        id=str(uuid4()),
        user_id=user.id,
        credential_id=b"cred-old",
        public_key=b"pk",
        sign_count=0,
        flagged_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    session.add(cred)
    await session.commit()

    f = await F.signcount_regression_recent(sm)
    assert f is None


# ---------------------------------------------------------------------------
# passkey_synced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passkey_synced_info_finding(sm, session: AsyncSession):
    user = await _seed_user(session)
    cred = WebAuthnCredential(
        id=str(uuid4()),
        user_id=user.id,
        credential_id=b"cred-sync",
        public_key=b"pk",
        sign_count=0,
        backup_state="synced",
        backup_eligible=True,
    )
    session.add(cred)
    await session.commit()

    f = await F.passkey_synced(sm)
    assert f is not None
    assert f.severity == "info"


@pytest.mark.asyncio
async def test_passkey_synced_none_when_no_synced(sm, session: AsyncSession):
    """No synced credential present -- finding should be None."""
    user = await _seed_user(session)
    cred = WebAuthnCredential(
        id=str(uuid4()),
        user_id=user.id,
        credential_id=b"cred-nosync",
        public_key=b"pk",
        sign_count=0,
        backup_state=None,
        backup_eligible=False,
    )
    session.add(cred)
    await session.commit()

    f = await F.passkey_synced(sm)
    assert f is None


# ---------------------------------------------------------------------------
# tls_self_signed (stub)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tls_self_signed_stub_returns_none(sm):
    f = await F.tls_self_signed(sm)
    assert f is None


# ---------------------------------------------------------------------------
# secrets_root_key_colocated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_secrets_root_key_colocated_finding(sm, tmp_path):
    # DB and secrets dir share a parent prefix → flag.
    settings = FleetSettings(
        db_url=f"sqlite+aiosqlite:///{tmp_path}/fleet.db",
        secrets_root_dir=str(tmp_path / "secrets"),
        secrets_root_key_b64="abc",
    )
    f = await F.secrets_root_key_colocated(sm, settings=settings)
    assert f is not None
    assert f.severity == "high"


@pytest.mark.asyncio
async def test_secrets_root_key_colocated_none_when_unset(sm, tmp_path):
    settings = FleetSettings(
        db_url=f"sqlite+aiosqlite:///{tmp_path}/fleet.db",
        secrets_root_dir=None,
        secrets_root_key_b64=None,
    )
    f = await F.secrets_root_key_colocated(sm, settings=settings)
    assert f is None


@pytest.mark.asyncio
async def test_secrets_root_key_colocated_none_when_distinct(sm):
    settings = FleetSettings(
        db_url="sqlite+aiosqlite:////var/lib/hl/fleet.db",
        secrets_root_dir="/etc/hl/secrets",
        secrets_root_key_b64="abc",
    )
    f = await F.secrets_root_key_colocated(sm, settings=settings)
    assert f is None


# ---------------------------------------------------------------------------
# vault_unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vault_unreachable_no_broker_returns_none(sm):
    f = await F.vault_unreachable(sm, broker=None)
    assert f is None


@pytest.mark.asyncio
async def test_vault_unreachable_no_vault_backend_returns_none(sm):
    broker = mock.MagicMock()
    broker.backends = {"local": mock.MagicMock()}
    f = await F.vault_unreachable(sm, broker=broker)
    assert f is None


@pytest.mark.asyncio
async def test_vault_unreachable_sealed_finding(sm):
    vault = mock.MagicMock()

    async def hc():
        return {"sealed": True, "initialized": True, "version": "1.0"}

    vault.health_check = hc
    broker = mock.MagicMock()
    broker.backends = {"vault": vault}

    f = await F.vault_unreachable(sm, broker=broker)
    assert f is not None
    assert f.severity == "critical"


@pytest.mark.asyncio
async def test_vault_unreachable_raises_finding(sm):
    vault = mock.MagicMock()

    async def hc():
        raise RuntimeError("connection refused")

    vault.health_check = hc
    broker = mock.MagicMock()
    broker.backends = {"vault": vault}

    f = await F.vault_unreachable(sm, broker=broker)
    assert f is not None
    assert f.severity == "critical"


@pytest.mark.asyncio
async def test_vault_unreachable_error_summary_is_generic(sm):
    """Vault error summary must not leak exception details."""
    vault = mock.MagicMock()

    async def hc():
        raise RuntimeError("connection to vault.internal:8200 refused")

    vault.health_check = hc
    broker = mock.MagicMock()
    broker.backends = {"vault": vault}
    f = await F.vault_unreachable(sm, broker=broker)
    assert f is not None
    assert "vault.internal" not in f.summary
    assert "connection" not in f.summary.lower() or "check server logs" in f.summary.lower()


# ---------------------------------------------------------------------------
# mfa_recency_disabled_for_high_risk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mfa_recency_populated_no_finding(sm):
    f = await F.mfa_recency_disabled_for_high_risk(sm)
    assert f is None


@pytest.mark.asyncio
async def test_mfa_recency_empty_finding(sm, monkeypatch):
    monkeypatch.setattr(
        "server.app.auth.mfa.policy._HIGH_RISK_VERBS", frozenset()
    )
    monkeypatch.setattr(
        "server.app.auth.mfa.policy._HIGH_RISK_PREFIXES", frozenset()
    )
    f = await F.mfa_recency_disabled_for_high_risk(sm)
    assert f is not None
    assert f.severity == "medium"


@pytest.mark.asyncio
async def test_mfa_recency_prefixes_only_no_finding(sm, monkeypatch):
    """Finding should NOT fire when prefixes are set but verbs are empty."""
    monkeypatch.setattr(
        "server.app.auth.mfa.policy._HIGH_RISK_VERBS", frozenset()
    )
    monkeypatch.setattr(
        "server.app.auth.mfa.policy._HIGH_RISK_PREFIXES", frozenset({"bootstrap."})
    )
    f = await F.mfa_recency_disabled_for_high_risk(sm)
    assert f is None


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_posture_admin_required(sm):
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/posture")
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_posture_happy_path_sorted(sm, session: AsyncSession, auth_headers):
    # Seed a local-admin (medium) and a flagged credential (high).
    role = await _seed_admin_role(session)
    user = await _seed_user(session, kind=UserKind.LOCAL)
    await _seed_binding(session, user=user, role=role)
    cred = WebAuthnCredential(
        id=str(uuid4()),
        user_id=user.id,
        credential_id=b"cred-x",
        public_key=b"pk",
        sign_count=0,
        flagged_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    session.add(cred)
    await session.commit()

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/v1/posture", headers=auth_headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert "findings" in body
            ids = [f["id"] for f in body["findings"]]
            sevs = [f["severity"] for f in body["findings"]]
            # Sorted: critical > high > medium > low > info
            order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            assert sevs == sorted(sevs, key=lambda s: order[s])
            assert "signcount_regression_recent" in ids
            # local_password_admins_exist may also be present
            assert "local_password_admins_exist" in ids


@pytest.mark.asyncio
async def test_posture_partial_failure_still_returns_200(sm, session: AsyncSession, auth_headers):
    """When one finding function throws, the endpoint still returns 200 with other findings."""
    role = await _seed_admin_role(session)
    user = await _seed_user(session, kind=UserKind.LOCAL)
    await _seed_binding(session, user=user, role=role)

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    with mock.patch.object(F, "tls_self_signed", side_effect=RuntimeError("kaboom")):
        with mock.patch(
            "server.app.api.middleware.admin_auth.load_settings",
            return_value=FleetSettings(admin_token=SecretStr(ADMIN_TOKEN)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                r = await c.get("/v1/posture", headers=auth_headers)
                assert r.status_code == 200
                body = r.json()
                assert "findings" in body
                ids = [f["id"] for f in body["findings"]]
                assert "local_password_admins_exist" in ids


def test_registry_lists_all_findings():
    # Sanity: registry should contain at least the 9 finding functions.
    assert len(ALL_FINDINGS) >= 9


def test_finding_dataclass_frozen():
    f = Finding(id="x", severity="info", title="t", summary="s")
    with pytest.raises(Exception):
        f.id = "y"  # type: ignore[misc]
