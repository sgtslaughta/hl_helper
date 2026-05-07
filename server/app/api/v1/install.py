"""Installation script endpoint."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.state import get_app_state
from server.app.enrollment.tokens import hash_token
from server.app.models.agent_release import (
    AgentRelease,
    ReleaseChannel,
    ReleaseStatus,
)
from server.app.models.enrollment_token import EnrollmentToken

router = APIRouter(prefix="/v1", tags=["install"])

# Architectures the bootstrap endpoint will resolve.
_ALLOWED_ARCHES = {"amd64", "arm64", "armv7"}
_ALLOWED_OSES = {"linux", "darwin"}


async def _validate_enrollment_token(token: str, db: AsyncSession) -> EnrollmentToken:
    """Look up an enrollment token by plaintext, ensure it is live.

    Live = exists, not yet redeemed (or non-one-time), not expired.
    Returns the token row; raises HTTPException(401) on any failure.

    Use this from the bootstrap install path: the token authorizes
    binary download + signed-manifest fetch ahead of `/v1/enroll` consuming it.
    """
    if not token:
        raise HTTPException(status_code=401, detail="missing enrollment token")
    h = hash_token(token)
    row = (
        await db.execute(select(EnrollmentToken).where(EnrollmentToken.token_hash == h))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid enrollment token")
    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(status_code=401, detail="enrollment token expired")
    if row.one_time and row.redeemed_at is not None:
        raise HTTPException(status_code=401, detail="enrollment token already redeemed")
    return row


@router.get("/install/agent-release-info")
async def install_release_info(
    request: Request,
    token: str = Query(...),
    os: str = Query(...),
    arch: str = Query(...),
):
    """Resolve latest release for (os, arch). Requires a live enrollment token.

    Returns release id + version + sha256 so the install script can verify
    the binary it downloads. Bound to enrollment token to keep the registry
    catalog from being enumerated by anonymous callers.
    """
    if os not in _ALLOWED_OSES:
        raise HTTPException(status_code=400, detail=f"unsupported os: {os}")
    if arch not in _ALLOWED_ARCHES:
        raise HTTPException(status_code=400, detail=f"unsupported arch: {arch}")
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        await _validate_enrollment_token(token, session)
        stmt = (
            select(AgentRelease)
            .where(
                AgentRelease.os == os,
                AgentRelease.arch == arch,
                AgentRelease.channel == ReleaseChannel.STABLE,
                AgentRelease.status == ReleaseStatus.PUBLISHED,
            )
            .order_by(AgentRelease.uploaded_at.desc())
            .limit(1)
        )
        rel = (await session.execute(stmt)).scalar_one_or_none()
        if rel is None:
            raise HTTPException(status_code=404, detail="no published release")
        return {
            "id": str(rel.id),
            "version": rel.version,
            "sha256": rel.sha256,
            "size": rel.size,
            "manifest_json": rel.manifest_json.decode(),
            "manifest_sig_hex": rel.manifest_sig.hex(),
        }


@router.get("/install/agent-binary")
async def install_agent_binary(
    request: Request,
    token: str = Query(...),
    os: str = Query(...),
    arch: str = Query(...),
):
    """Stream the agent binary for bootstrap install. Enrollment-token gated.

    Looks up the latest published release for (os, arch), verifies the
    binary file exists in HL_AGENT_DIST_DIR, and streams it. Sets
    X-SHA256 and X-Release-Version headers so the installer can verify
    integrity against the signed manifest.
    """
    if os not in _ALLOWED_OSES:
        raise HTTPException(status_code=400, detail=f"unsupported os: {os}")
    if arch not in _ALLOWED_ARCHES:
        raise HTTPException(status_code=400, detail=f"unsupported arch: {arch}")
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        await _validate_enrollment_token(token, session)
        stmt = (
            select(AgentRelease)
            .where(
                AgentRelease.os == os,
                AgentRelease.arch == arch,
                AgentRelease.channel == ReleaseChannel.STABLE,
                AgentRelease.status == ReleaseStatus.PUBLISHED,
            )
            .order_by(AgentRelease.uploaded_at.desc())
            .limit(1)
        )
        rel = (await session.execute(stmt)).scalar_one_or_none()
        if rel is None:
            raise HTTPException(status_code=404, detail="no published release")

        # Capture before session closes — StreamingResponse outlives session.
        version = rel.version
        rel_os = rel.os
        rel_arch = rel.arch
        sha256 = rel.sha256
        size = rel.size

    import os as _os

    base = (
        Path(_os.environ.get("HL_AGENT_DIST_DIR", "/var/lib/hl-helper/agent-dist"))
        / "releases"
        / version
        / f"{rel_os}-{rel_arch}"
    )
    path = base / "hl-agent"
    if not path.exists():
        raise HTTPException(status_code=410, detail="binary missing on server")

    def _iter():
        with path.open("rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type="application/octet-stream",
        headers={
            "X-SHA256": sha256,
            "X-Release-Version": version,
            "Content-Length": str(size),
        },
    )

# Unprefixed alias so older copy-pasted curl commands like
#   curl -fsSL <origin>/install.sh | sh
# continue to work alongside the canonical /v1/install.sh path.
alias_router = APIRouter(tags=["install"])


@router.get("/install.sh", response_class=Response)
async def get_install_script(
    request: Request,
    token: str = "",
    server: str = "",
    grpc_endpoint: str = "",
) -> Response:
    """Get install.sh script, rendered with query params and signed.

    Args:
        token: Enrollment token (optional)
        server: Server hostname (optional, defaults to request host)

    Returns:
        Shell script with X-Install-Signature header containing base64 signature
    """
    from server.app.api.state import get_app_state

    state = get_app_state(request)

    # Default server to request host if not provided
    if not server:
        server = request.url.hostname or "localhost"

    # Load and render template
    template_dir = Path(__file__).parent.parent.parent.parent / "templates"
    # autoescape disabled: template renders POSIX shell, not HTML/XML.
    # Body is signed via Ed25519 (X-Install-Signature header) for tamper detection.
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)  # nosec B701
    template = env.get_template("install.sh.j2")
    rendered = template.render(
        token=token, server=server, SERVER=server, grpc_endpoint=grpc_endpoint
    )

    # Sign the rendered script
    rendered_bytes = rendered.encode("utf-8")
    signature = state.signing_backend.sign(rendered_bytes)
    signature_b64 = base64.b64encode(signature).decode("ascii")

    return Response(
        content=rendered,
        media_type="text/plain",
        headers={"X-Install-Signature": signature_b64},
    )


@alias_router.get("/install.sh", response_class=Response)
async def get_install_script_alias(
    request: Request,
    token: str = "",
    server: str = "",
    grpc_endpoint: str = "",
) -> Response:
    """Alias for /v1/install.sh at root path."""
    return await get_install_script(
        request, token=token, server=server, grpc_endpoint=grpc_endpoint
    )
