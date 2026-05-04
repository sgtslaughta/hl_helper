"""Authentication endpoints: login, logout, whoami, refresh."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from server.app.api.state import get_app_state
from server.app.auth.lockout import LockoutTrackerPersistent
from server.app.auth.password import PasswordHasher
from server.app.auth.sessions import make_request_meta
from server.app.auth.transports import extract_token
from server.app.deps import current_principal
from server.app.models import User
from server.app.rbac.provider import Principal
from server.app.settings.config import load_settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ============================================================================
# Pydantic Models
# ============================================================================


class LoginRequest(BaseModel):
    """Login request with username or email + password."""

    model_config = {"extra": "forbid"}

    username: str | None = None
    email: str | None = None
    password: str


class LoginResponse(BaseModel):
    """Successful login response with session token."""

    session_token: str
    expires_at: datetime


class MfaChallengeResponse(BaseModel):
    """MFA challenge response (for future MFA support)."""

    mfa_challenge_id: str
    methods: list[str]


class WhoamiResponse(BaseModel):
    """Current principal info."""

    id: str
    email: str
    roles: list[str] = []
    groups: list[str] = []


class RefreshResponse(BaseModel):
    """Refresh response with updated session info (expires_at only)."""

    expires_at: datetime


# ============================================================================
# Helpers
# ============================================================================


def _user_has_mfa(user: User) -> bool:
    """Stub: check if user has MFA configured. Always returns False for now."""
    return False


def _request_meta(request: Request) -> dict[str, str]:
    """Extract request metadata (IP and User-Agent) for audit/session tracking."""
    return {
        "ip": request.client.host if request.client else "0.0.0.0",
        "ua": request.headers.get("user-agent", ""),
    }


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/login", status_code=200, response_model=None)
async def login(
    body: LoginRequest,
    request: Request,
) -> LoginResponse | Response:
    """POST /v1/auth/login — authenticate and issue session.

    Body:
        {username or email, password}

    Returns:
        200 {session_token, expires_at} with cookies set if MFA not required.
        202 {mfa_challenge_id, methods} if MFA required (stub, returns 200 for now).

    Raises:
        401: Invalid credentials.
        423: Account locked.
        500: Internal server error.
    """
    app_state = get_app_state(request)

    settings = load_settings()

    # Look up user by email or username
    user = None
    async with app_state.sessionmaker() as db_session:
        if body.email:
            user = await db_session.scalar(select(User).where(User.email == body.email))
        elif body.username:
            # For now, treat username as email lookup
            user = await db_session.scalar(select(User).where(User.email == body.username))

    if not user:
        log.info("login_failed", reason="user_not_found", identifier=body.email or body.username)
        # Emit audit event (user not found)
        meta = _request_meta(request)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="anonymous",
                    action="auth.login.failed",
                    subject=body.email or body.username,
                    payload={"reason": "user_not_found", "ip": meta["ip"], "ua_present": bool(meta["ua"])},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Check lockout
    lockout_tracker = LockoutTrackerPersistent(sessionmaker=app_state.sessionmaker)
    lockout_key = f"user:{user.id}"
    if await lockout_tracker.is_locked(lockout_key):
        log.warning("login_locked", user_id=user.id)
        # Emit audit event (lockout)
        meta = _request_meta(request)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="anonymous",
                    action="auth.login.failed",
                    subject=user.id,
                    payload={"reason": "lockout", "ip": meta["ip"], "ua_present": bool(meta["ua"])},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account locked")

    # Verify password
    hasher = PasswordHasher(
        time_cost=settings.password_argon2_time_cost,
        memory_cost=settings.password_argon2_memory_kib,
        parallelism=settings.password_argon2_parallelism,
    )

    if not user.password_hash or not hasher.verify(user.password_hash, body.password):
        await lockout_tracker.record_failure(lockout_key)
        log.info("login_failed", user_id=user.id, reason="invalid_password")
        # Emit audit event (wrong password)
        meta = _request_meta(request)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="anonymous",
                    action="auth.login.failed",
                    subject=user.id,
                    payload={"reason": "wrong_password", "ip": meta["ip"], "ua_present": bool(meta["ua"])},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Record success and clear lockout
    await lockout_tracker.record_success(lockout_key)
    log.info("login_success", user_id=user.id)

    # Emit audit event (success)
    meta = _request_meta(request)
    async with app_state.sessionmaker() as audit_session:
        try:
            await app_state.audit_chain.append(
                audit_session,
                actor=user.id,
                action="auth.login.success",
                subject=user.id,
                payload={"ip": meta["ip"], "ua_present": bool(meta["ua"])},
            )
            await audit_session.commit()
        except Exception as e:
            log.exception("audit_append_failed", exc=e)

    # Check MFA requirement (stub: always False for now)
    if _user_has_mfa(user):
        # Return 202 with MFA challenge (not implemented yet)
        return Response(
            status_code=status.HTTP_202_ACCEPTED,
            content=MfaChallengeResponse(
                mfa_challenge_id="stub", methods=["totp"]
            ).model_dump_json(),
        )

    # Issue session
    meta = _request_meta(request)
    request_meta = make_request_meta(ip=meta["ip"], ua=meta["ua"])
    if app_state.session_service is None:
        raise HTTPException(status_code=503, detail="session service not configured")
    session_issue = await app_state.session_service.issue(user, "none", request_meta)

    # Generate CSRF token
    csrf_token = secrets.token_urlsafe(32)

    # Create response with cookies
    response = Response(
        status_code=status.HTTP_200_OK,
        content=LoginResponse(
            session_token=session_issue.raw,
            expires_at=session_issue.expires_at,
        ).model_dump_json(),
    )

    # Set session cookie (HttpOnly, Secure, SameSite=Lax)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_issue.raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int((session_issue.expires_at - datetime.now(timezone.utc)).total_seconds()),
    )

    # Set CSRF cookie (NOT HttpOnly, so JS can read for double-submit)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int((session_issue.expires_at - datetime.now(timezone.utc)).total_seconds()),
    )

    return response


@router.post("/logout", status_code=204)
async def logout(
    principal: Annotated[Principal | None, Depends(current_principal)],
    request: Request,
) -> Response:
    """POST /v1/auth/logout — revoke session and clear cookies.

    Returns:
        204 No Content.

    Raises:
        401: Not authenticated.
    """
    if principal is None or principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    settings = load_settings()
    app_state = get_app_state(request)

    # Extract token and revoke the session
    token, _source = extract_token(request)
    if token and app_state.session_service:
        session = await app_state.session_service.lookup(token, request_meta=None)
        if session:
            await app_state.session_service.revoke(session.id, reason="logout")

    log.info("logout", user_id=principal.user_id)

    # Emit audit event (logout)
    async with app_state.sessionmaker() as audit_session:
        try:
            await app_state.audit_chain.append(
                audit_session,
                actor=principal.user_id,
                action="auth.logout",
                subject=principal.user_id,
                payload={},
            )
            await audit_session.commit()
        except Exception as e:
            log.exception("audit_append_failed", exc=e)

    # Clear cookies
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=settings.session_cookie_name)
    response.delete_cookie(key=settings.csrf_cookie_name)

    return response


@router.get("/whoami", status_code=200)
async def whoami(
    principal: Annotated[Principal | None, Depends(current_principal)],
    app_state: Annotated[Any, Depends(get_app_state)],
) -> WhoamiResponse:
    """GET /v1/auth/whoami — return current principal info.

    Returns:
        200 {id, email, roles, groups}.

    Raises:
        401: Not authenticated.
    """
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Fetch user info
    async with app_state.sessionmaker() as db_session:
        user = await db_session.scalar(select(User).where(User.id == principal.user_id))

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return WhoamiResponse(
        id=user.id,
        email=user.email,
        roles=[],  # TODO(c3-rbac-wire): populate from bindings
        groups=[],  # TODO(c3-rbac-wire): populate from groups
    )


@router.post("/refresh", status_code=200)
async def refresh(
    principal: Annotated[Principal | None, Depends(current_principal)],
    app_state: Annotated[Any, Depends(get_app_state)],
) -> RefreshResponse:
    """POST /v1/auth/refresh — no-op refresh (sliding TTL on each lookup).

    Returns:
        200 {session_token, expires_at}.

    Raises:
        401: Not authenticated.
    """
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # This is a no-op for now since sliding TTL happens on every lookup.
    # Return placeholder data.
    settings = load_settings()
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    expires_at = now + timedelta(seconds=settings.session_abs_ttl_s)

    return RefreshResponse(expires_at=expires_at)
