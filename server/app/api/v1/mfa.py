"""MFA endpoint routes -- TOTP, WebAuthn, recovery, challenge, credential mgmt.

Shared helpers + Pydantic schemas live in _mfa_common.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from server.app.auth.mfa.totp import TotpService

from server.app.api.state import get_app_state
from server.app.api.v1._mfa_common import (
    ChallengeRequest,
    ChallengeResponse,
    CredentialOut,
    RecoveryRegenerateResponse,
    SignCountRegression,
    TotpEnrollBeginResponse,
    TotpEnrollFinishRequest,
    WebAuthnCredential,
    WebAuthnEnrollBeginRequest,
    _WEBAUTHN_AVAILABLE,
    _WEBAUTHN_MODEL_AVAILABLE,
    assert_mfa_recency,
    emit_audit,
    make_webauthn,
    recovery_service,
    require_user,
    totp_service,
    user_has_existing_mfa,
)
from server.app.auth.mfa.plugin import _registry as _mfa_plugin_registry
from server.app.auth.mfa.recovery import RecoveryCooldown
from server.app.deps import current_principal
from server.app.models import User
from server.app.rbac.provider import Principal

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/mfa", tags=["mfa"])



@router.post("/totp/enroll-begin", response_model=TotpEnrollBeginResponse)
async def totp_enroll_begin(
    request: Request,
    principal: Annotated[Principal | None, Depends(current_principal)],
) -> TotpEnrollBeginResponse:
    user = await require_user(request, principal)
    svc = totp_service(request)
    out = await svc.enroll_begin(user)
    await emit_audit(
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
    user = await require_user(request, principal)
    # Step-up required only if user already has an MFA factor (avoid chicken-and-egg
    # for first-time enrollment).
    app_state = get_app_state(request)
    if await user_has_existing_mfa(app_state, user.id):
        await assert_mfa_recency(request, user, "mfa.totp.enroll_finish")
    svc = totp_service(request)
    ok = await svc.enroll_finish(user, body.code)
    if not ok:
        raise HTTPException(status_code=400, detail="invalid_totp_code")
    await emit_audit(
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
    user = await require_user(request, principal)
    app_state = get_app_state(request)
    svc = make_webauthn(app_state)
    options = await svc.registration_begin(user, name=body.name)
    await emit_audit(
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
    user = await require_user(request, principal)
    app_state = get_app_state(request)
    svc = make_webauthn(app_state)
    await svc.registration_finish(user, body)
    await emit_audit(
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
    user = await require_user(request, principal)
    verified = False

    async def _audit_failed(reason: str) -> None:
        await emit_audit(
            request, actor=user.id, action="mfa.challenge.failed",
            subject=user.id, payload={"method": body.method, "reason": reason},
        )

    if body.method == "totp":
        if not isinstance(body.proof, str):
            await _audit_failed("proof_must_be_string")
            raise HTTPException(status_code=400, detail="proof_must_be_string")
        svc = totp_service(request)
        try:
            verified = await svc.verify(user, body.proof)
        except TotpService.TotpCooldown:
            await _audit_failed("totp_cooldown")
            raise HTTPException(status_code=429, detail="totp_cooldown")
    elif body.method == "recovery":
        if not isinstance(body.proof, str):
            await _audit_failed("proof_must_be_string")
            raise HTTPException(status_code=400, detail="proof_must_be_string")
        rsvc = recovery_service(request)
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
        svc = make_webauthn(app_state)
        try:
            verified = bool(await svc.assertion_finish(user, body.proof))
        except SignCountRegression as e:
            await emit_audit(
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

    await emit_audit(
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
    user = await require_user(request, principal)
    await assert_mfa_recency(request, user, "mfa.recovery.regenerate")
    rsvc = recovery_service(request)
    codes = await rsvc.regenerate(user)
    await emit_audit(
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
    user = await require_user(request, principal)
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
    user = await require_user(request, principal)
    await assert_mfa_recency(request, user, "mfa.credential.delete")
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
    await emit_audit(
        request, actor=user.id, action="mfa.credential.delete",
        subject=credential_id, payload={},
    )
    return Response(status_code=204)
