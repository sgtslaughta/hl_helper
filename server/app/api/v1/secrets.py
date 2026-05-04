"""Secrets API: CRUD and management for encrypted secrets."""

from __future__ import annotations

import base64
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.deps import current_principal
from server.app.rbac.provider import Principal
from server.app.secrets.ref import SecretRef
from server.app.secrets.broker import ReAuthRequired
from server.app.secrets.backends.base import BackendSealed

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/secrets", tags=["secrets"])


# ============================================================================
# Pydantic Models
# ============================================================================


class SecretRefOut(BaseModel):
    """Secret reference with version info."""

    ref: str = Field(..., description="Secret URI")
    versions: list[int] = Field(default_factory=list, description="Available versions")


class SecretPutRequest(BaseModel):
    """Request to write a secret."""

    ref: str = Field(..., description="Secret URI (secret://backend/path)")
    value: str = Field(..., description="Secret value (base64-encoded)")


class SecretRotateRequest(BaseModel):
    """Request to rotate a secret."""

    ref: str = Field(..., description="Secret URI to rotate")


class SecretRevealRequest(BaseModel):
    """Request to reveal secret plaintext."""

    ref: str = Field(..., description="Secret URI to reveal")


class SecretMigrateRequest(BaseModel):
    """Request to migrate secret between backends."""

    src_ref: str = Field(..., description="Source secret URI")
    dst_ref: str = Field(..., description="Destination secret URI")
    dry_run: bool = Field(default=True, description="Simulate migration without writing")


class SecretMigrateResponse(BaseModel):
    """Response from migration operation."""

    migrated: bool = Field(..., description="Whether migration succeeded")
    bytes: int = Field(..., description="Size of secret value migrated")


class SecretRevealResponse(BaseModel):
    """Response from reveal operation."""

    value: str = Field(..., description="Secret value (base64-encoded)")


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=list[SecretRefOut])
async def list_secrets(
    request: Request,
    _: str = Depends(admin_required),
) -> list[SecretRefOut]:
    """List available secrets (admin only).

    Requires admin Bearer token in Authorization header.

    Returns:
        List of secret refs with version info
    """
    app_state = get_app_state(request)

    if app_state.secrets_broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secrets backend not configured",
        )

    # For now, return empty list as enumeration requires backend-specific logic
    return []


@router.post("", status_code=status.HTTP_201_CREATED)
async def put_secret(
    request: Request,
    body: SecretPutRequest,
    _: str = Depends(admin_required),
    principal: Principal | None = Depends(current_principal),
) -> dict[str, Any]:
    """Write a secret (admin only).

    Requires admin Bearer token in Authorization header.

    Args:
        body: Request with ref and base64-encoded value

    Returns:
        Success response with version number
    """
    app_state = get_app_state(request)

    if app_state.secrets_broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secrets backend not configured",
        )

    try:
        ref = SecretRef.parse(body.ref)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Decode base64 value
    try:
        value = base64.b64decode(body.value)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid base64 value: {e}",
        )

    broker: Any = app_state.secrets_broker
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required")
    requester = principal

    try:
        version = await broker.put(ref, value, requester)
        return {"version": version, "ref": str(ref)}
    except Exception as e:
        log.exception("secret_put_failed", exc=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write secret",
        )


@router.post("/actions/rotate", status_code=status.HTTP_200_OK)
async def rotate_secret(
    request: Request,
    body: SecretRotateRequest,
    _: str = Depends(admin_required),
    principal: Principal | None = Depends(current_principal),
) -> dict[str, Any]:
    """Rotate a secret (admin only).

    Bumps the version by invalidating cache.

    Args:
        body: Request with ref to rotate

    Returns:
        Success response
    """
    app_state = get_app_state(request)

    if app_state.secrets_broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secrets backend not configured",
        )

    try:
        ref = SecretRef.parse(body.ref)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    broker: Any = app_state.secrets_broker
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required")
    requester = principal

    try:
        version = await broker.rotate(ref, requester)
        return {"ref": str(ref), "rotated": True, "version": version}
    except Exception as e:
        log.exception("secret_rotate_failed", exc=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate secret",
        )


@router.post("/actions/reveal", response_model=SecretRevealResponse)
async def reveal_secret(
    request: Request,
    body: SecretRevealRequest,
    _: str = Depends(admin_required),
    principal: Principal | None = Depends(current_principal),
) -> SecretRevealResponse:
    """Reveal secret plaintext (requires X-MFA-Proof header).

    Returns base64-encoded plaintext. Requires valid X-MFA-Proof header.

    Args:
        body: Request with ref to reveal

    Returns:
        Secret value as base64
    """
    app_state = get_app_state(request)

    if app_state.secrets_broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secrets backend not configured",
        )

    # Check for MFA proof
    mfa_proof = request.headers.get("X-MFA-Proof")
    if not mfa_proof:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="mfa_required",
        )

    try:
        ref = SecretRef.parse(body.ref)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    broker: Any = app_state.secrets_broker
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required")
    requester = principal

    try:
        verifier = getattr(app_state, "mfa_proof_verifier", None)
        mfa_ok = verifier(mfa_proof, requester) if verifier else _verify_mfa_proof(mfa_proof, requester)
        if not mfa_ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid MFA proof",
            )

        # Get handle (no re-auth needed for stub)
        h = await broker.get(ref, requester)
        value = await broker.reveal(h, requester)

        return SecretRevealResponse(value=base64.b64encode(value).decode())
    except ReAuthRequired:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fresh MFA required",
        )
    except BackendSealed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="vault_sealed_degraded",
        )
    except HTTPException:
        raise
    except Exception as e:
        log.exception("secret_reveal_failed", exc=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reveal secret",
        )


@router.post(
    "/actions/migrate",
    response_model=SecretMigrateResponse,
    dependencies=[Depends(admin_required)],
)
async def migrate_secret(
    request: Request,
    body: SecretMigrateRequest,
    principal: Principal | None = Depends(current_principal),
) -> SecretMigrateResponse:
    """Migrate secret from one backend to another (admin only).

    Supports dry-run mode to simulate without writing.
    Audit logs the migration regardless of dry_run flag.

    Args:
        body: Request with src_ref, dst_ref, dry_run flag

    Returns:
        Success response with byte count
    """
    app_state = get_app_state(request)

    if app_state.secrets_broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secrets backend not configured",
        )

    try:
        src_ref = SecretRef.parse(body.src_ref)
        dst_ref = SecretRef.parse(body.dst_ref)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    broker: Any = app_state.secrets_broker
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required")
    requester = principal

    try:
        # Read from source
        value = await broker._raw_get(src_ref)
        byte_count = len(value)

        # Audit the migration intent (regardless of dry_run)
        if broker.audit_chain is not None:
            try:
                await broker.audit_chain.append(
                    session=None,
                    actor=requester.user_id,
                    action="secret.migrated",
                    subject=f"{src_ref} -> {dst_ref}",
                    payload={"src_ref": str(src_ref), "dst_ref": str(dst_ref), "dry_run": body.dry_run, "bytes": byte_count},
                )
            except Exception as e:
                log.exception("audit_failed", exc=e)

        # Write to destination (unless dry-run)
        if not body.dry_run:
            await broker.put(dst_ref, value, requester)

        return SecretMigrateResponse(migrated=not body.dry_run, bytes=byte_count)
    except Exception as e:
        log.exception("secret_migrate_failed", exc=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to migrate secret",
        )


# ============================================================================
# Helpers
# ============================================================================


def _verify_mfa_proof(proof: str, principal: Any) -> bool:
    """Verify MFA proof -- FAIL-CLOSED stub.

    Always returns False until wired to real MFA verification.
    Production must configure a real verifier before enabling reveal.

    @param proof: MFA proof string
    @param principal: Requester principal
    @return: Always False (fail-closed)
    """
    # TODO(security): Wire to real MFA verification (TOTP challenge, session step-up).
    # Until then, reveal is blocked by design.
    return False
