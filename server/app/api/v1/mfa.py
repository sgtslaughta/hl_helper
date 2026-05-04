"""MFA endpoints — TOTP, WebAuthn, recovery, challenge, credential mgmt."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from server.app.api.state import get_app_state
from server.app.auth.mfa.plugin import _registry as _mfa_plugin_registry
from server.app.auth.mfa.recovery import RecoveryCooldown, RecoveryService
from server.app.auth.mfa.totp import TotpService
from server.app.deps import current_principal
from server.app.models import TotpSecret, User
from server.app.rbac.provider import Principal

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/mfa", tags=["mfa"])


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


# ============================================================================
# Pydantic models
# ============================================================================


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


# ============================================================================
# Helpers
# ============================================================================


async def _require_user(
    request: Request,
    principal: Principal | None,
) -> User:
    """Return the authenticated user row, or raise 401."""
    if principal is None or principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        user = await session.scalar(select(User).where(User.id == principal.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    return user


async def _emit_audit(request: Request, *, actor: str, action: str, subject: str | None, payload: dict[str, Any]) -> None:
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


def _totp_service(request: Request) -> TotpService:
    app_state = get_app_state(request)
    # Use a 32-byte AES-GCM key for at-rest encryption. For tests, derive one.
    enc_key = getattr(app_state, "totp_enc_key", None) or b"\x00" * 32
    return TotpService(sessionmaker=app_state.sessionmaker, encryption_key=enc_key)


def _recovery_service(request: Request) -> RecoveryService:
    app_state = get_app_state(request)
    return RecoveryService(sessionmaker=app_state.sessionmaker)


async def _user_has_existing_mfa(app_state: Any, user_id: str) -> bool:
    """Return True iff user has a CONFIRMED TotpSecret OR any WebAuthnCredential row.

    Pending (unconfirmed) TotpSecret rows do NOT count — first-time enroll-finish
    must succeed without prior MFA recency.
    """
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


def _raise_step_up() -> None:
    raise HTTPException(
        status_code=401,
        detail="mfa_step_up_required",
        headers={"X-MFA-Required": "true"},
    )


_MFA_MGMT_RECENCY_SECONDS = 300


async def _assert_mfa_recency(request: Request, user: User, verb: str) -> None:
    """Enforce MFA recency for high-risk MFA-management endpoints.

    These endpoints (recovery regen, credential delete, totp enroll-finish on
    re-enroll) always require fresh MFA — they are not gated by MfaPolicy's
    verb prefix table because they manage MFA itself.
    """
    last = getattr(user, "last_mfa_at", None)
    fresh = False
    if last is not None:
        ts = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - ts).total_seconds() <= _MFA_MGMT_RECENCY_SECONDS:
            fresh = True
    if not fresh:
        await _emit_audit(
            request, actor=user.id, action="mfa.step_up.required",
            subject=user.id, payload={"verb": verb},
        )
        _raise_step_up()


def _make_webauthn(app_state: Any) -> Any:
    """Return the singleton WebAuthnService (cached on app_state).

    The service holds an in-memory challenge store; a fresh instance per
    request would lose challenges between begin/finish ceremonies. We cache
    it lazily on `app_state.webauthn_service` and back the challenge dict
    with `app_state.webauthn_challenges` so even if the service is rebuilt
    (e.g. tests reset it) the store survives.

    RP id is derived from settings (`webauthn_rp_id`) or, failing that,
    from the public URL host. Origin defaults to scheme://host of the
    public URL.
    """
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
        except Exception:  # pragma: no cover - frozen dataclass fallback
            pass

    svc = WebAuthnService(
        sessionmaker=app_state.sessionmaker,
        rp_id=rp_id,
        origin=origin,
        challenge_store=challenge_store,
    )
    try:
        app_state.webauthn_service = svc
    except Exception:  # pragma: no cover - frozen dataclass fallback
        pass
    return svc


# ============================================================================
# TOTP endpoints
# ============================================================================


@router.post("/totp/enroll-begin", response_model=TotpEnrollBeginResponse)
async def totp_enroll_begin(
    request: Request,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> TotpEnrollBeginResponse:
    user = await _require_user(request, principal)
    svc = _totp_service(request)
    out = await svc.enroll_begin(user)
    await _emit_audit(
        request, actor=user.id, action="mfa.totp.enroll_begin",
        subject=user.id, payload={},
    )
    return TotpEnrollBeginResponse(
        secret_b32=out.secret_b32,
        provisioning_uri=out.provisioning_uri,
        qr_svg=None,
    )


@router.post("/totp/enroll-finish", status_code=204)
async def totp_enroll_finish(
    request: Request,
    body: TotpEnrollFinishRequest,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> Response:
    user = await _require_user(request, principal)
    # Step-up required only if user already has an MFA factor (avoid chicken-and-egg
    # for first-time enrollment).
    app_state = get_app_state(request)
    if await _user_has_existing_mfa(app_state, user.id):
        await _assert_mfa_recency(request, user, "mfa.totp.enroll_finish")
    svc = _totp_service(request)
    ok = await svc.enroll_finish(user, body.code)
    if not ok:
        raise HTTPException(status_code=400, detail="invalid_totp_code")
    await _emit_audit(
        request, actor=user.id, action="mfa.totp.enroll_finish",
        subject=user.id, payload={},
    )
    return Response(status_code=204)


# ============================================================================
# WebAuthn endpoints (guarded)
# ============================================================================


@router.post("/webauthn/enroll-begin")
async def webauthn_enroll_begin(
    request: Request,
    body: WebAuthnEnrollBeginRequest,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> dict[str, Any]:
    if not _WEBAUTHN_AVAILABLE:
        raise HTTPException(status_code=503, detail="webauthn_unavailable")
    user = await _require_user(request, principal)
    app_state = get_app_state(request)
    svc = _make_webauthn(app_state)
    options = await svc.registration_begin(user, name=body.name)
    await _emit_audit(
        request, actor=user.id, action="mfa.webauthn.enroll_begin",
        subject=user.id, payload={"name": body.name},
    )
    return options if isinstance(options, dict) else dict(options)


@router.post("/webauthn/enroll-finish", status_code=204)
async def webauthn_enroll_finish(
    request: Request,
    body: dict[str, Any],
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> Response:
    if not _WEBAUTHN_AVAILABLE:
        raise HTTPException(status_code=503, detail="webauthn_unavailable")
    user = await _require_user(request, principal)
    app_state = get_app_state(request)
    svc = _make_webauthn(app_state)
    await svc.registration_finish(user, body)
    await _emit_audit(
        request, actor=user.id, action="mfa.webauthn.enroll_finish",
        subject=user.id, payload={},
    )
    return Response(status_code=204)


# ============================================================================
# Challenge
# ============================================================================


@router.post("/challenge", response_model=ChallengeResponse)
async def challenge(
    request: Request,
    body: ChallengeRequest,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> ChallengeResponse:
    user = await _require_user(request, principal)
    verified = False

    async def _audit_failed(reason: str) -> None:
        await _emit_audit(
            request, actor=user.id, action="mfa.challenge.failed",
            subject=user.id, payload={"method": body.method, "reason": reason},
        )

    if body.method == "totp":
        if not isinstance(body.proof, str):
            await _audit_failed("proof_must_be_string")
            raise HTTPException(status_code=400, detail="proof_must_be_string")
        svc = _totp_service(request)
        try:
            verified = await svc.verify(user, body.proof)
        except TotpService.TotpCooldown:
            await _audit_failed("totp_cooldown")
            raise HTTPException(status_code=429, detail="totp_cooldown")
    elif body.method == "recovery":
        if not isinstance(body.proof, str):
            await _audit_failed("proof_must_be_string")
            raise HTTPException(status_code=400, detail="proof_must_be_string")
        rsvc = _recovery_service(request)
        try:
            verified = await rsvc.consume(user, body.proof)
        except RecoveryCooldown:
            await _audit_failed("recovery_cooldown")
            raise HTTPException(status_code=429, detail="recovery_cooldown")
    elif body.method == "webauthn":
        if not _WEBAUTHN_AVAILABLE:
            await _audit_failed("webauthn_unavailable")
            raise HTTPException(status_code=503, detail="webauthn_unavailable")
        if not isinstance(body.proof, dict):
            await _audit_failed("proof_must_be_object")
            raise HTTPException(status_code=400, detail="proof_must_be_object")
        app_state = get_app_state(request)
        svc = _make_webauthn(app_state)
        try:
            verified = bool(await svc.assertion_finish(user, body.proof))
        except SignCountRegression as e:
            await _emit_audit(
                request,
                actor=user.id,
                action="mfa.webauthn.signcount_regression",
                subject=user.id,
                payload={"error": str(e)},
            )
            raise HTTPException(
                status_code=401, detail="webauthn_signcount_regression"
            )
    else:
        # Plugin path: route via MfaPluginRegistry.
        plugin = _mfa_plugin_registry.get(body.method)
        if plugin is None:
            await _audit_failed("unknown_method")
            raise HTTPException(status_code=401, detail="mfa_verification_failed")
        if not isinstance(body.proof, dict):
            await _audit_failed("proof_must_be_object")
            raise HTTPException(status_code=400, detail="proof_must_be_object")
        try:
            verified = bool(await plugin.verify(user, body.proof))
        except Exception:
            await _audit_failed("plugin_error")
            raise HTTPException(status_code=502, detail="mfa_plugin_error")
        # Plugin path relies on global rate-limiter for brute-force protection.
        # Per-method cooldowns are the plugin's responsibility.

    if not verified:
        await _audit_failed("verification_failed")
        raise HTTPException(status_code=401, detail="mfa_verification_failed")

    # Update last_mfa_at on user. Commit failure must NOT report verified=True.
    app_state = get_app_state(request)
    try:
        async with app_state.sessionmaker() as session:
            u = await session.scalar(select(User).where(User.id == user.id))
            if u is not None:
                u.last_mfa_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as e:
        log.exception("mfa_challenge_commit_failed", exc=e)
        await _audit_failed("commit_failed")
        raise HTTPException(status_code=500, detail="mfa_commit_failed")

    await _emit_audit(
        request, actor=user.id, action="mfa.challenge.success",
        subject=user.id, payload={"method": body.method},
    )
    return ChallengeResponse(verified=True)


# ============================================================================
# Recovery
# ============================================================================


@router.post("/recovery/regenerate", response_model=RecoveryRegenerateResponse)
async def recovery_regenerate(
    request: Request,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> RecoveryRegenerateResponse:
    user = await _require_user(request, principal)
    await _assert_mfa_recency(request, user, "mfa.recovery.regenerate")
    rsvc = _recovery_service(request)
    codes = await rsvc.regenerate(user)
    await _emit_audit(
        request, actor=user.id, action="mfa.recovery.regenerate",
        subject=user.id, payload={"count": len(codes)},
    )
    return RecoveryRegenerateResponse(codes=codes)


# ============================================================================
# Credential management
# ============================================================================


@router.get("/credentials", response_model=list[CredentialOut])
async def list_credentials(
    request: Request,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> list[CredentialOut]:
    user = await _require_user(request, principal)
    if not _WEBAUTHN_MODEL_AVAILABLE:
        return []
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        rows = (
            await session.scalars(
                select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
            )
        ).all()
    return [
        CredentialOut(
            id=r.id,
            name=getattr(r, "name", "") or "",
            created_at=r.created_at,
            last_used_at=getattr(r, "last_used_at", None),
        )
        for r in rows
    ]


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    request: Request,
    credential_id: str,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> Response:
    user = await _require_user(request, principal)
    await _assert_mfa_recency(request, user, "mfa.credential.delete")
    if not _WEBAUTHN_MODEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="webauthn_unavailable")
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        cred = await session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.id == credential_id)
        )
        if cred is None:
            raise HTTPException(status_code=404, detail="credential_not_found")
        if cred.user_id != user.id:
            # Treat cross-user access as not-found to avoid disclosure.
            raise HTTPException(status_code=404, detail="credential_not_found")
        await session.delete(cred)
        await session.commit()
    await _emit_audit(
        request, actor=user.id, action="mfa.credential.delete",
        subject=credential_id, payload={},
    )
    return Response(status_code=204)
