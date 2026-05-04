"""Bootstrap endpoint for first-owner provisioning via bootstrap token."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update

from server.app.api.state import get_app_state
from server.app.auth.password import PasswordHasher, validate_password
from server.app.auth.sessions import make_request_meta
from server.app.models import BootstrapToken, User
from server.app.models.binding import Binding, PrincipalType, ScopeKind
from server.app.models.role import Role
from server.app.models.user import UserKind
from server.app.settings.config import load_settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/bootstrap", tags=["bootstrap"])


# ============================================================================
# Helpers
# ============================================================================


def _request_meta(request: Request) -> dict[str, str]:
    """Extract request metadata (IP and User-Agent) for audit/session tracking."""
    return {
        "ip": request.client.host if request.client else "0.0.0.0",
        "ua": request.headers.get("user-agent", ""),
    }


def _compute_scope_hash(kind: str, value: dict[str, object]) -> str:
    """Compute scope_hash from kind and value."""
    import json
    canon = json.dumps({"kind": kind, "value": value}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


# ============================================================================
# Pydantic Models
# ============================================================================


class BootstrapOwnerRequest(BaseModel):
    """Bootstrap owner creation request."""

    model_config = {"extra": "forbid"}

    token: str
    email: str
    password: str


class BootstrapOwnerResponse(BaseModel):
    """Successful bootstrap response with session token."""

    session_token: str
    expires_at: datetime


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/owner", status_code=200, response_model=None)
async def bootstrap_owner(
    request: Request,
    body: BootstrapOwnerRequest,
    app_state: Annotated[Any, Depends(get_app_state)],
) -> BootstrapOwnerResponse | Response:
    """POST /v1/bootstrap/owner — provision first admin via bootstrap token.

    Body:
        {token, email, password}

    Returns:
        200 {session_token, expires_at} with cookies set.

    Raises:
        400: Invalid password complexity.
        410: Token not found, expired, or already consumed.
        500: Internal server error.
    """

    settings = load_settings()

    # Hash the provided token (sha256)
    token_hash = hashlib.sha256(body.token.encode("utf-8")).digest()
    now = datetime.now(timezone.utc)

    # Validate password complexity before transaction
    complexity_errors = validate_password(body.password, user_context={"email": body.email})
    if complexity_errors:
        log.info("bootstrap_owner_failed", reason="weak_password", errors=complexity_errors)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password too weak: {', '.join(complexity_errors)}",
        )

    # Create User (kind="local")
    hasher = PasswordHasher(
        time_cost=settings.password_argon2_time_cost,
        memory_cost=settings.password_argon2_memory_kib,
        parallelism=settings.password_argon2_parallelism,
    )
    password_hash = hasher.hash(body.password)

    new_user = User(
        email=body.email,
        kind=UserKind.LOCAL,
        password_hash=password_hash,
    )

    # All-in-one transaction: validate token, consume it, create user, bind to owner role
    async with app_state.sessionmaker() as db_session:
        # Update token to consume it atomically (use UPDATE ... WHERE ... AND consumed_at IS NULL)
        result = await db_session.execute(
            update(BootstrapToken)
            .where(
                (BootstrapToken.token_hash == token_hash)
                & (BootstrapToken.consumed_at.is_(None))
                & (BootstrapToken.expires_at > now)
            )
            .values(consumed_at=now)
        )

        if result.rowcount == 0:
            # Token was either consumed concurrently, expired, or unknown
            # Determine which case for logging
            bootstrap_token = await db_session.scalar(
                select(BootstrapToken).where(BootstrapToken.token_hash == token_hash)
            )
            if not bootstrap_token:
                log.warning("bootstrap_owner_failed", reason="token_not_found")
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token not found or invalid")

            expires_at = bootstrap_token.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                log.warning("bootstrap_owner_failed", reason="token_expired", token_id=bootstrap_token.id)
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

            if bootstrap_token.consumed_at is not None:
                log.warning("bootstrap_owner_failed", reason="token_already_consumed", token_id=bootstrap_token.id)
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token already consumed")

            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token not found or invalid")

        # Add new user to session
        db_session.add(new_user)
        await db_session.flush()  # Flush to get user.id but don't commit yet

        # Query for owner role
        owner_role = await db_session.scalar(
            select(Role).where(Role.name == "owner")
        )

        if not owner_role:
            # Owner role doesn't exist (rare), create it as fallback
            log.warning("bootstrap_owner: owner role not found, creating fallback")
            owner_role = Role(
                name="owner",
                description="Owner role (bootstrap fallback)",
                built_in=True,
                permissions=[],
            )
            db_session.add(owner_role)
            await db_session.flush()

        # Bind user to owner role with global scope
        scope_hash = _compute_scope_hash("global", {})
        binding = Binding(
            principal_type=PrincipalType.USER,
            principal_id=new_user.id,
            role_id=owner_role.id,
            scope_kind=ScopeKind.GLOBAL,
            scope_value={},
            scope_hash=scope_hash,
        )
        db_session.add(binding)

        # Commit all together
        await db_session.commit()

    log.info("bootstrap_owner_success", user_id=new_user.id, email=body.email)

    # Emit audit event
    meta = _request_meta(request)
    async with app_state.sessionmaker() as audit_session:
        try:
            await app_state.audit_chain.append(
                audit_session,
                actor=new_user.id,
                action="bootstrap.owner_created",
                subject=new_user.id,
                payload={"email": body.email, "ip": meta["ip"], "ua_present": bool(meta["ua"])},
            )
            await audit_session.commit()
        except Exception as e:
            log.exception("audit_append_failed", exc=e)

    # Issue session
    meta = _request_meta(request)
    request_meta = make_request_meta(ip=meta["ip"], ua=meta["ua"])
    session_issue = await app_state.session_service.issue(new_user, "none", request_meta)

    # Generate CSRF token
    csrf_token = secrets.token_urlsafe(32)

    # Create response with cookies
    response = Response(
        status_code=status.HTTP_200_OK,
        content=BootstrapOwnerResponse(
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
        max_age=int((session_issue.expires_at - now).total_seconds()),
    )

    # Set CSRF cookie (NOT HttpOnly, so JS can read for double-submit)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int((session_issue.expires_at - now).total_seconds()),
    )

    return response
