"""WebAuthn MFA service — FIDO2 / passkey registration and assertion.

Wraps py_webauthn (`webauthn` package). Per-user registration and
authentication challenges are kept in a module-level dictionary with a
5-minute TTL. Persistence is via the `WebAuthnCredential` SQLAlchemy
model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.exceptions import InvalidAuthenticationResponse
from webauthn.helpers.structs import (
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
)

from server.app.models import User, WebAuthnCredential

logger = logging.getLogger(__name__)

_CHALLENGE_TTL = timedelta(minutes=5)


class SignCountRegression(Exception):
    """Raised when an authenticator's reported sign-count goes backwards.

    This may indicate a cloned authenticator. The corresponding credential
    row is flagged via `flagged_at`.
    """


@dataclass
class _StoredChallenge:
    challenge: bytes
    created_at: datetime
    name: str = ""


class WebAuthnService:
    """WebAuthn registration + assertion using py_webauthn."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        rp_id: str,
        rp_name: str = "hl_helper",
        origin: str | None = None,
        challenge_store: dict[str, _StoredChallenge] | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.origin = origin or f"https://{rp_id}"
        # Allow callers to inject a shared challenge store so begin/finish
        # ceremonies survive across distinct WebAuthnService instances
        # (e.g. one constructed per HTTP request). Defaults to per-instance.
        self._challenges: dict[str, _StoredChallenge] = (
            challenge_store if challenge_store is not None else {}
        )

    # ---------- registration ----------

    async def registration_begin(self, user: User, name: str) -> dict[str, Any]:
        """Begin a WebAuthn registration ceremony.

        Returns a dict with `options` (jsonable) and the raw `challenge` bytes.
        """
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=user.id.encode("utf-8"),
            user_name=user.email,
            user_display_name=user.email,
        )
        self._challenges[user.id] = _StoredChallenge(
            challenge=options.challenge,
            created_at=datetime.now(timezone.utc),
            name=name,
        )
        opts_dict = cast(dict[str, Any], json.loads(options_to_json(options)))
        return {"options": opts_dict, "challenge": options.challenge}

    async def registration_finish(
        self, user: User, credential_response: dict[str, Any]
    ) -> WebAuthnCredential:
        """Complete a registration ceremony; persist the credential row."""
        stored = self._get_challenge(user)
        name = stored.name

        verified = verify_registration_response(
            credential=credential_response,
            expected_challenge=stored.challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
        )

        backup_state = "backed_up" if verified.credential_backed_up else "not_backed_up"
        # Transports come from the client response under .response.transports
        # per the WebAuthn spec (and verified.transports if py_webauthn surfaces it).
        transports_raw: list[str] = []
        verified_transports = getattr(verified, "transports", None)
        if verified_transports:
            transports_raw = [
                t.value if hasattr(t, "value") else str(t) for t in verified_transports
            ]
        else:
            response_obj = credential_response.get("response") or {}
            if isinstance(response_obj, dict):
                transports_raw = list(response_obj.get("transports", []) or [])
        # Normalise enum format to its string value (e.g. "none" not
        # "AttestationFormat.NONE").
        fmt_obj = verified.fmt
        attestation_fmt = fmt_obj.value if hasattr(fmt_obj, "value") else str(fmt_obj)
        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            aaguid=verified.aaguid or "",
            transports=transports_raw,
            backup_state=backup_state,
            backup_eligible=bool(verified.credential_backed_up),
            name=name,
            attestation_fmt=attestation_fmt,
        )
        async with self.sessionmaker() as session:
            session.add(cred)
            await session.commit()
            await session.refresh(cred)

        # one-shot challenge
        self._challenges.pop(user.id, None)
        return cred

    # ---------- assertion ----------

    async def assertion_begin(self, user: User) -> dict[str, Any]:
        """Begin an authentication ceremony; return options + challenge."""
        async with self.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
                )
            ).scalars().all()

        allow = [
            PublicKeyCredentialDescriptor(
                id=row.credential_id,
                transports=[
                    AuthenticatorTransport(t) for t in row.transports if _is_known_transport(t)
                ]
                or None,
            )
            for row in rows
        ]
        options = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=allow or None,
        )
        self._challenges[user.id] = _StoredChallenge(
            challenge=options.challenge,
            created_at=datetime.now(timezone.utc),
        )
        opts_dict = cast(dict[str, Any], json.loads(options_to_json(options)))
        return {"options": opts_dict, "challenge": options.challenge}

    async def assertion_finish(
        self, user: User, assertion_response: dict[str, Any]
    ) -> bool:
        """Complete an assertion. Returns True on success.

        Raises SignCountRegression if the new sign-count is strictly less
        than the stored value (and flags the credential row).
        """
        stored = self._get_challenge(user)

        # Locate the matching credential by id (raw bytes from response.rawId
        # is base64url; py_webauthn handles decoding inside verify_*). We
        # need the credential_public_key + current_sign_count up-front, so
        # we look up by what the caller hands us. Tests inject a mocked
        # verify result, so we just iterate user creds and pick the first
        # one whose verify returns matching credential_id.
        async with self.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
                )
            ).scalars().all()
            if not rows:
                return False

            last_exc: InvalidAuthenticationResponse | None = None
            for row in rows:
                try:
                    verified = verify_authentication_response(
                        credential=assertion_response,
                        expected_challenge=stored.challenge,
                        expected_rp_id=self.rp_id,
                        expected_origin=self.origin,
                        credential_public_key=row.public_key,
                        credential_current_sign_count=row.sign_count,
                    )
                except InvalidAuthenticationResponse as e:
                    # Verification failed for this row (signature, challenge,
                    # origin, RP id, etc). Try the next stored credential.
                    # Anything else (DB errors, SignCountRegression) must
                    # propagate to the caller.
                    last_exc = e
                    continue
                if verified.credential_id != row.credential_id:
                    continue
                # Sign-count regression check — flag, commit, then raise so
                # the persisted flag survives even if the caller swallows
                # the exception.
                if verified.new_sign_count < row.sign_count:
                    row.flagged_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.warning(
                        "webauthn_sign_count_regression",
                        extra={
                            "credential_id": row.id,
                            "user_id": row.user_id,
                            "stored_sign_count": row.sign_count,
                            "new_sign_count": verified.new_sign_count,
                        },
                    )
                    raise SignCountRegression(
                        f"sign_count regressed for credential {row.id}: "
                        f"stored={row.sign_count} new={verified.new_sign_count}"
                    )
                row.sign_count = verified.new_sign_count
                row.last_used_at = datetime.now(timezone.utc)
                await session.commit()
                self._challenges.pop(user.id, None)
                return True

            if last_exc is not None:
                # No credential matched; surface as failure.
                return False
            return False

    # ---------- helpers ----------

    def _get_challenge(self, user: User) -> _StoredChallenge:
        stored = self._challenges.get(user.id)
        if stored is None:
            raise LookupError(f"No active WebAuthn challenge for user {user.id}")
        if datetime.now(timezone.utc) - stored.created_at > _CHALLENGE_TTL:
            self._challenges.pop(user.id, None)
            raise LookupError(f"WebAuthn challenge expired for user {user.id}")
        return stored


def _is_known_transport(value: str) -> bool:
    try:
        AuthenticatorTransport(value)
    except ValueError:
        return False
    return True


# Re-export for tests / patching at module boundary.
__all__ = [
    "SignCountRegression",
    "WebAuthnService",
    "verify_registration_response",
    "verify_authentication_response",
]


# Suppress "imported but unused" — these are part of the public surface
# specifically for monkeypatching in tests.
_ = (verify_registration_response, verify_authentication_response)
