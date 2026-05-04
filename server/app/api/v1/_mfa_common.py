"""Shared schemas + helpers for MFA endpoints (TOTP, WebAuthn, recovery)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import structlog
from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from server.app.api.state import get_app_state
from server.app.auth.mfa.recovery import RecoveryService
from server.app.auth.mfa.totp import TotpService
from server.app.models import TotpSecret, User
from server.app.rbac.provider import Principal

log = structlog.get_logger(__name__)


# Optional WebAuthn module — parallel agent may land it later.
try:  # pragma: no cover - import-time guard
    from server.app.auth.mfa.webauthn import (
        SignCountRegression as _SignCountRegression,
        WebAuthnService as _WebAuthnService,
    )

    WebAuthnService: Any = _WebAuthnService
    SignCountRegression: Any = _SignCountRegression
    _WEBAUTHN_AVAILABLE = True
except ImportError:
    WebAuthnService = None
    SignCountRegression = None
    _WEBAUTHN_AVAILABLE = False

try:  # pragma: no cover
    from server.app.models import WebAuthnCredential as _WebAuthnCredential

    WebAuthnCredential: Any = _WebAuthnCredential
    _WEBAUTHN_MODEL_AVAILABLE = True
except ImportError:
    WebAuthnCredential = None
    _WEBAUTHN_MODEL_AVAILABLE = False


# Pydantic models


class TotpEnrollBeginResponse(BaseModel):
    secret_b32: str
    provisioning_uri: str
    qr_svg: str | None = None


class TotpEnrollFinishRequest(BaseModel):
    model_config = {"extra": "forbid"}
    code: str


class WebAuthnEnrollBeginRequest(BaseModel):
    model_config = {"extra": "forbid"}
    name: str


class ChallengeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    method: str
    proof: Any


class ChallengeResponse(BaseModel):
    verified: bool


class RecoveryRegenerateResponse(BaseModel):
    codes: list[str]


class CredentialOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None


# Helpers


async def require_user(
    request: Request,
    principal: Principal | None,
) -> User:
    if principal is None or principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        user = await session.scalar(select(User).where(User.id == principal.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    return user


async def emit_audit(
    request: Request,
    *,
    actor: str,
    action: str,
    subject: str | None,
    payload: dict[str, Any],
) -> None:
    app_state = get_app_state(request)
    if app_state.audit_chain is None:
        return
    async with app_state.sessionmaker() as audit_session:
        try:
            await app_state.audit_chain.append(
                audit_session,
                actor=actor,
                action=action,
                subject=subject,
                payload=payload,
            )
            await audit_session.commit()
        except Exception as e:  # pragma: no cover
            log.exception("audit_append_failed", exc=e)


def totp_service(request: Request) -> TotpService:
    app_state = get_app_state(request)
    enc_key = getattr(app_state, "totp_enc_key", None) or b"\x00" * 32
    return TotpService(sessionmaker=app_state.sessionmaker, encryption_key=enc_key)


def recovery_service(request: Request) -> RecoveryService:
    app_state = get_app_state(request)
    return RecoveryService(sessionmaker=app_state.sessionmaker)


async def user_has_existing_mfa(app_state: Any, user_id: str) -> bool:
    async with app_state.sessionmaker() as session:
        totp = await session.scalar(
            select(TotpSecret).where(
                TotpSecret.user_id == user_id,
                TotpSecret.confirmed_at.is_not(None),
            )
        )
        if totp is not None:
            return True
        if _WEBAUTHN_MODEL_AVAILABLE:
            cred = await session.scalar(
                select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
            )
            if cred is not None:
                return True
    return False


def raise_step_up() -> None:
    raise HTTPException(
        status_code=401,
        detail="mfa_step_up_required",
        headers={"X-MFA-Required": "true"},
    )


MFA_MGMT_RECENCY_SECONDS = 300


async def assert_mfa_recency(request: Request, user: User, verb: str) -> None:
    """Enforce MFA recency for MFA-management endpoints (always fresh)."""
    last = getattr(user, "last_mfa_at", None)
    fresh = False
    if last is not None:
        ts = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - ts).total_seconds() <= MFA_MGMT_RECENCY_SECONDS:
            fresh = True
    if not fresh:
        await emit_audit(
            request,
            actor=user.id,
            action="mfa.step_up.required",
            subject=user.id,
            payload={"verb": verb},
        )
        raise_step_up()


def make_webauthn(app_state: Any) -> Any:
    """Return cached singleton WebAuthnService (challenge store survives rebuilds)."""
    cached = getattr(app_state, "webauthn_service", None)
    if cached is not None:
        return cached

    rp_id = getattr(app_state, "webauthn_rp_id", None)
    origin = getattr(app_state, "webauthn_origin", None)
    public_url = getattr(app_state, "fleet_public_url", None) or getattr(
        app_state, "public_url", None
    )
    if (rp_id is None or origin is None) and public_url:
        parsed = urlparse(public_url)
        if rp_id is None and parsed.hostname:
            rp_id = parsed.hostname
        if origin is None and parsed.scheme and parsed.hostname:
            host = parsed.hostname
            if parsed.port:
                host = f"{host}:{parsed.port}"
            origin = f"{parsed.scheme}://{host}"
    rp_id = rp_id or "localhost"

    challenge_store = getattr(app_state, "webauthn_challenges", None)
    if challenge_store is None:
        challenge_store = {}
        try:
            app_state.webauthn_challenges = challenge_store
        except Exception:  # pragma: no cover
            pass

    svc = WebAuthnService(
        sessionmaker=app_state.sessionmaker,
        rp_id=rp_id,
        origin=origin,
        challenge_store=challenge_store,
    )
    try:
        app_state.webauthn_service = svc
    except Exception:  # pragma: no cover
        pass
    return svc
