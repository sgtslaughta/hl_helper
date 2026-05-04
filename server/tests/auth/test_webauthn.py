"""Tests for WebAuthn MFA service.

These tests mock at the module boundary
(`server.app.auth.mfa.webauthn.verify_registration_response` and
`server.app.auth.mfa.webauthn.verify_authentication_response`) because
generating real attestation/assertion blobs requires a live authenticator.
This is the documented, recommended fallback per the task spec.
"""

from __future__ import annotations

import os
from typing import AsyncIterator
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.auth.mfa.webauthn import (
    SignCountRegression,
    WebAuthnService,
)
from server.app.db.session import make_engine, make_sessionmaker
from server.app.models import User, WebAuthnCredential
from server.app.models.base import Base as BaseModel


@pytest.fixture
async def engine():
    e = make_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield e
    await e.dispose()


@pytest.fixture
async def sm(engine) -> async_sessionmaker:
    return make_sessionmaker(engine)


@pytest.fixture
async def session(sm) -> AsyncIterator[AsyncSession]:
    async with sm() as s:
        yield s
        await s.rollback()


@pytest.fixture
async def user(session: AsyncSession) -> User:
    u = User(id="user-wa-1", email="webauthn@example.com", kind="local")
    session.add(u)
    await session.commit()
    return u


@pytest.fixture
def service(sm) -> WebAuthnService:
    return WebAuthnService(
        sm,
        rp_id="example.com",
        rp_name="hl_helper",
        origin="https://example.com",
    )


class _FakeVerifiedRegistration:
    """Stand-in for webauthn.helpers.structs.VerifiedRegistration."""

    def __init__(
        self,
        credential_id: bytes,
        public_key: bytes,
        sign_count: int = 0,
        aaguid: str = "00000000-0000-0000-0000-000000000000",
        fmt: str = "none",
        credential_backed_up: bool = False,
    ) -> None:
        self.credential_id = credential_id
        self.credential_public_key = public_key
        self.sign_count = sign_count
        self.aaguid = aaguid
        self.fmt = fmt
        self.credential_backed_up = credential_backed_up
        self.credential_device_type = "single_device"
        self.user_verified = True


class _FakeVerifiedAuthentication:
    def __init__(self, credential_id: bytes, new_sign_count: int) -> None:
        self.credential_id = credential_id
        self.new_sign_count = new_sign_count
        self.credential_device_type = "single_device"
        self.credential_backed_up = False
        self.user_verified = True


class TestRegistrationBegin:
    async def test_returns_options_with_challenge_rp_id_user_id(
        self, service: WebAuthnService, user: User
    ) -> None:
        out = await service.registration_begin(user, name="my-key")
        options = out["options"]
        assert "challenge" in options
        assert options["rp"]["id"] == "example.com"
        assert options["user"]["id"]  # base64url of user id bytes
        # challenge persisted
        assert user.id in service._challenges
        assert service._challenges[user.id].challenge == out["challenge"]


class TestRegistrationFinish:
    async def test_persists_credential_row(
        self, service: WebAuthnService, user: User, session: AsyncSession
    ) -> None:
        await service.registration_begin(user, name="my-key")
        cred_id = os.urandom(32)
        pub = os.urandom(64)
        fake_verified = _FakeVerifiedRegistration(cred_id, pub, sign_count=0, aaguid="aaaa-bbbb")
        with patch(
            "server.app.auth.mfa.webauthn.verify_registration_response",
            return_value=fake_verified,
        ):
            cred = await service.registration_finish(
                user,
                {"id": "stub", "rawId": "stub", "response": {}, "type": "public-key"},
            )
        assert cred.credential_id == cred_id
        assert cred.public_key == pub
        assert cred.aaguid == "aaaa-bbbb"
        assert cred.name == "my-key"
        # row in DB
        row = await session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
        )
        assert row is not None
        assert row.credential_id == cred_id


class TestAssertionBegin:
    async def test_returns_challenge_and_allow_credentials(
        self, service: WebAuthnService, user: User, session: AsyncSession
    ) -> None:
        cred_id_a = os.urandom(32)
        cred_id_b = os.urandom(32)
        for cid in (cred_id_a, cred_id_b):
            session.add(
                WebAuthnCredential(
                    user_id=user.id,
                    credential_id=cid,
                    public_key=os.urandom(32),
                    sign_count=0,
                    aaguid="x",
                    transports=["usb"],
                    backup_state="not_backed_up",
                    backup_eligible=False,
                    name="k",
                    attestation_fmt="none",
                )
            )
        await session.commit()

        out = await service.assertion_begin(user)
        options = out["options"]
        assert "challenge" in options
        assert len(options["allowCredentials"]) == 2


class TestAssertionFinish:
    async def test_validates_and_bumps_sign_count(
        self, service: WebAuthnService, user: User, session: AsyncSession
    ) -> None:
        cred_id = os.urandom(32)
        pub = os.urandom(32)
        session.add(
            WebAuthnCredential(
                user_id=user.id,
                credential_id=cred_id,
                public_key=pub,
                sign_count=3,
                aaguid="x",
                transports=["usb"],
                backup_state="not_backed_up",
                backup_eligible=False,
                name="k",
                attestation_fmt="none",
            )
        )
        await session.commit()

        await service.assertion_begin(user)
        with patch(
            "server.app.auth.mfa.webauthn.verify_authentication_response",
            return_value=_FakeVerifiedAuthentication(cred_id, new_sign_count=7),
        ):
            ok = await service.assertion_finish(
                user,
                {
                    "id": "stub",
                    "rawId": "stub",
                    "response": {},
                    "type": "public-key",
                },
            )
        assert ok is True
        row = await session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cred_id)
        )
        assert row is not None
        assert row.sign_count == 7
        assert row.last_used_at is not None


class TestSignCountRegression:
    async def test_raises_and_flags_credential(
        self, service: WebAuthnService, user: User, session: AsyncSession
    ) -> None:
        cred_id = os.urandom(32)
        session.add(
            WebAuthnCredential(
                user_id=user.id,
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

        await service.assertion_begin(user)
        with patch(
            "server.app.auth.mfa.webauthn.verify_authentication_response",
            return_value=_FakeVerifiedAuthentication(cred_id, new_sign_count=5),
        ):
            with pytest.raises(SignCountRegression):
                await service.assertion_finish(
                    user,
                    {"id": "s", "rawId": "s", "response": {}, "type": "public-key"},
                )
        row = await session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cred_id)
        )
        assert row is not None
        assert row.flagged_at is not None


class TestMultiCredential:
    async def test_two_registrations_show_in_assertion_begin(
        self, service: WebAuthnService, user: User, session: AsyncSession
    ) -> None:
        # registration 1
        await service.registration_begin(user, name="k1")
        cid1 = os.urandom(32)
        with patch(
            "server.app.auth.mfa.webauthn.verify_registration_response",
            return_value=_FakeVerifiedRegistration(cid1, os.urandom(32)),
        ):
            await service.registration_finish(
                user, {"id": "s", "rawId": "s", "response": {}, "type": "public-key"}
            )

        # registration 2
        await service.registration_begin(user, name="k2")
        cid2 = os.urandom(32)
        with patch(
            "server.app.auth.mfa.webauthn.verify_registration_response",
            return_value=_FakeVerifiedRegistration(cid2, os.urandom(32)),
        ):
            await service.registration_finish(
                user, {"id": "s", "rawId": "s", "response": {}, "type": "public-key"}
            )

        out = await service.assertion_begin(user)
        assert len(out["options"]["allowCredentials"]) == 2
