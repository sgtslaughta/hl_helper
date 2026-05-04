"""C3 negative-suite E2E tests — auth + secrets edge cases.

Covers TOTP replay, WebAuthn sign-count regression, OIDC state mismatch
and replay, secret reveal without re-auth, local backend tamper, vault
sealed degraded mode, password lockout, role-binding session invalidation,
and webauthn-only policy gating.

Where features are not yet shipped (e.g., 5.7 sealed monitor) the tests
guard with importorskip / skipif and a clear reason.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Tuple
from unittest.mock import patch

import httpx
import pyotp
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.api.app import create_app
from server.app.auth.mfa.policy import MfaPolicy
from server.app.auth.mfa.totp import TotpService
from server.app.auth.mfa.webauthn import SignCountRegression, WebAuthnService
from server.app.auth.oidc.client import OidcError, OidcStateStore
from server.app.auth.password import PasswordHasher
from server.app.auth.sessions import SessionService
from server.app.events.bus import Bus
from server.app.models import User, WebAuthnCredential
from server.app.models.base import Base
from server.app.models.totp_secret import TotpSecret
from server.app.models.user import UserKind
from server.app.secrets.backends.base import IntegrityError
from server.app.secrets.backends.local import LocalEncryptedFileBackend
from server.app.secrets.broker import ReAuthRequired, SecretsBroker
from server.app.secrets.cache import BrokerCache
from server.app.secrets.handle import HandleStore
from server.app.secrets.ref import SecretRef
from server.tests._helpers.app_state import make_test_app_state


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
async def async_session_maker(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(async_session_maker, tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    bus = Bus()
    session_service = SessionService(sessionmaker=async_session_maker, bus=bus)
    await session_service.start()

    app.state.app_state = make_test_app_state(
        sessionmaker=async_session_maker,
        session_service=session_service,
        bus=bus,
        create_session_service=False,
        tmp_path=tmp_path,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c

    await session_service.stop()


@pytest.fixture
async def test_user(async_session_maker) -> Tuple[User, str]:
    hasher = PasswordHasher()
    password = "ValidPass123!@#"
    user = User(
        email="neg@example.com",
        kind=UserKind.LOCAL,
        password_hash=hasher.hash(password),
    )
    async with async_session_maker() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, password


async def _login(client: httpx.AsyncClient, user: User, password: str) -> Tuple[str, str]:
    resp = await client.post(
        "/v1/auth/login", json={"email": user.email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    csrf = resp.cookies.get("hls_csrf")
    assert csrf is not None
    return body["session_token"], csrf


# --------------------------------------------------------------------------- #
# 1) TOTP replay rejected
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_totp_replay_rejected(async_session_maker, test_user) -> None:
    """Second use of same TOTP step in same period must be rejected."""
    user, _ = test_user
    secret = pyotp.random_base32()
    # Persist a confirmed TotpSecret; encryption_key=None so verify uses _decrypt.
    # TotpService requires encryption_key for _encrypt path; persist plaintext bytes
    # via a dedicated 32-byte key.
    key = os.urandom(32)
    svc = TotpService(sessionmaker=async_session_maker, encryption_key=key)
    cipher = svc._encrypt(secret.encode())
    async with async_session_maker() as session:
        ts = TotpSecret(
            user_id=user.id,
            secret_ciphertext=cipher,
            algorithm="sha1",
            digits=6,
            period_s=30,
            confirmed_at=datetime.now(timezone.utc),
        )
        session.add(ts)
        await session.commit()

    code = pyotp.TOTP(secret).now()
    assert await svc.verify(user, code) is True
    # Second use of the SAME code (same step) must be rejected.
    assert await svc.verify(user, code) is False


# --------------------------------------------------------------------------- #
# 2) WebAuthn sign-count regression flags credential
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_webauthn_signcount_regression_flags_credential(
    async_session_maker,
) -> None:
    """Descending sign counter → SignCountRegression and credential flagged_at populated."""
    svc = WebAuthnService(
        async_session_maker,
        rp_id="example.com",
        rp_name="hl_helper",
        origin="https://example.com",
    )

    user_id = "user-wa-neg"
    cred_id = os.urandom(32)
    async with async_session_maker() as session:
        user = User(id=user_id, email="wa-neg@example.com", kind=UserKind.LOCAL)
        session.add(user)
        session.add(
            WebAuthnCredential(
                user_id=user_id,
                credential_id=cred_id,
                public_key=os.urandom(32),
                sign_count=10,
                aaguid="x",
                transports=["usb"],
                backup_state="not_backed_up",
                backup_eligible=False,
                name="k",
                attestation_fmt="none",
            )
        )
        await session.commit()
        await session.refresh(user)

    await svc.assertion_begin(user)

    class _FakeAuth:
        def __init__(self, cid: bytes, count: int) -> None:
            self.credential_id = cid
            self.new_sign_count = count
            self.credential_device_type = "single_device"
            self.credential_backed_up = False
            self.user_verified = True

    with patch(
        "server.app.auth.mfa.webauthn.verify_authentication_response",
        return_value=_FakeAuth(cred_id, 5),  # < stored 10 → regression
    ):
        with pytest.raises(SignCountRegression):
            await svc.assertion_finish(
                user,
                {"id": "s", "rawId": "s", "response": {}, "type": "public-key"},
            )

    async with async_session_maker() as session:
        row = await session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cred_id)
        )
        assert row is not None
        assert row.flagged_at is not None


# --------------------------------------------------------------------------- #
# 3) OIDC state mismatch rejected
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_oidc_state_mismatch_rejected() -> None:
    """Unknown state → OidcError state_not_found from store.consume."""
    store = OidcStateStore(ttl_seconds=60)
    with pytest.raises(OidcError, match="state_not_found"):
        await store.consume("never-issued-state")


# --------------------------------------------------------------------------- #
# 4) OIDC replayed code rejected (single-use state)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_oidc_replayed_code_rejected() -> None:
    """State already consumed → second consume rejected."""
    from server.app.auth.oidc.client import StateRecord

    store = OidcStateStore(ttl_seconds=60)
    rec = StateRecord(
        provider_id="p1",
        code_verifier="cv",
        nonce="n1",
        redirect_uri="https://app/cb",
        created_at=time.time(),
    )
    await store.put("st-rep", rec)
    got = await store.consume("st-rep")
    assert got.code_verifier == "cv"
    with pytest.raises(OidcError, match="state_not_found"):
        await store.consume("st-rep")


# --------------------------------------------------------------------------- #
# 5) Reveal without re-auth → ReAuthRequired (API: 401/403)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reveal_without_re_auth_403(tmp_path: Path) -> None:
    """broker.reveal w/o fresh MFA → ReAuthRequired."""
    backend = LocalEncryptedFileBackend(tmp_path, root_key=os.urandom(32))
    await backend.put("foo", b"value")
    cache = BrokerCache(ttl_seconds=30)
    handles = HandleStore()
    broker = SecretsBroker(
        backends={"local": backend},
        cache=cache,
        handle_store=handles,
        # mfa_recency_check=None → fail-closed in reveal()
    )

    class _Req:
        user_id = "u1"

    h = await broker.get(SecretRef.parse("secret://local/foo"), requester=_Req())
    with pytest.raises(ReAuthRequired):
        await broker.reveal(h, requester=_Req())


# --------------------------------------------------------------------------- #
# 6) Local disk tamper → IntegrityError
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_local_disk_tamper_aead_fails(tmp_path: Path) -> None:
    """Flip a byte in stored ciphertext → IntegrityError on get."""
    backend = LocalEncryptedFileBackend(tmp_path, root_key=os.urandom(32))
    await backend.put("foo", b"value")
    fpath = backend._path("foo", version=1)
    blob = fpath.read_bytes()
    # Pick a byte in the AEAD region (skip past header) and flip it.
    idx = max(0, len(blob) - 5)
    fpath.write_bytes(blob[:idx] + bytes([blob[idx] ^ 1]) + blob[idx + 1 :])
    with pytest.raises(IntegrityError):
        await backend.get("foo")


# --------------------------------------------------------------------------- #
# 7) Vault sealed → 503 after grace (5.7 not shipped → xfail)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_vault_sealed_returns_503_after_grace() -> None:
    """SealedModeMonitor in degraded → API 503.

    Task 5.7 (SealedModeMonitor) not yet shipped — module import will fail.
    """
    pytest.importorskip(
        "server.app.secrets.sealed",
        reason="Task 5.7 SealedModeMonitor not yet implemented",
    )
    # If the module exists in the future, expand this test to walk the
    # API path and assert 503. Until then, importorskip records skip.


# --------------------------------------------------------------------------- #
# 8) Password brute force → lockout 423
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_password_brute_force_locks_user(
    client: httpx.AsyncClient, test_user
) -> None:
    """5 wrong-password attempts → 6th returns 423 (LockoutTrackerPersistent)."""
    user, _ = test_user
    for _ in range(5):
        r = await client.post(
            "/v1/auth/login",
            json={"email": user.email, "password": "WrongPass!1"},
        )
        assert r.status_code == 401
    # 6th attempt: even with WRONG password we expect 423 (locked out).
    r = await client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "WrongPass!1"},
    )
    assert r.status_code == 423


# --------------------------------------------------------------------------- #
# 9) Session role-change → next request 401
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_session_role_change_invalidates(
    client: httpx.AsyncClient, test_user, async_session_maker
) -> None:
    """rbac.binding_changed → SessionService revokes; next request fails."""
    user, password = test_user
    token, _csrf = await _login(client, user, password)

    # Validate session works first.
    r = await client.get("/v1/auth/whoami", cookies={"hls_session": token})
    assert r.status_code == 200

    # Publish a binding-change event for this user.
    state = client._transport.app.state.app_state  # type: ignore[attr-defined]
    bus = state.bus
    await bus.publish("rbac.binding_changed", {"user_id": user.id})

    # Allow subscriber task to drain.
    import asyncio

    for _ in range(20):
        await asyncio.sleep(0.05)
        r = await client.get("/v1/auth/whoami", cookies={"hls_session": token})
        if r.status_code == 401:
            break
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 10) WebAuthn-only role rejects TOTP-only user (policy unit)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_webauthn_only_role_rejects_totp_only_user() -> None:
    """User with webauthn_only=True attr presenting only TOTP → policy False."""

    class _U:
        id = "u-x"
        webauthn_only = True

    policy = MfaPolicy()
    assert policy.webauthn_only_satisfied(_U(), ["totp"]) is False  # type: ignore[arg-type]
    assert policy.webauthn_only_satisfied(_U(), ["webauthn"]) is True  # type: ignore[arg-type]

    class _Permissive:
        id = "u-y"
        # default getattr -> False
    assert policy.webauthn_only_satisfied(_Permissive(), ["totp"]) is True  # type: ignore[arg-type]
