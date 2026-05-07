"""Agent releases CRUD: upload, list, manifest, download, yank."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models.agent_release import AgentRelease, ReleaseChannel, ReleaseStatus
from server.app.settings.config import load_settings

router = APIRouter(prefix="/v1/agent-releases", tags=["agent-releases"])

DOWNLOAD_TOKEN_TTL = timedelta(minutes=10)


def _get_session_secret() -> str:
    """Get a consistent secret for JWT operations.

    Uses a deterministic hash of admin_token if available, otherwise a test secret.
    """
    settings = load_settings()
    if settings.admin_token:
        token_str = settings.admin_token.get_secret_value()
        return hashlib.sha256(token_str.encode()).hexdigest()[:32]
    # Fallback for testing
    return "test-secret-key-change-in-prod"


def _release_dir() -> Path:
    """Get the base releases directory."""
    base = os.environ.get("HL_AGENT_DIST_DIR")
    if not base:
        base = "/var/lib/hl-helper/agent-dist"
    return Path(base) / "releases"


def _binary_path(version: str, os_: str, arch: str) -> Path:
    """Construct path to binary for a release."""
    return _release_dir() / version / f"{os_}-{arch}" / "hl-agent"


def _make_manifest(d: dict) -> bytes:
    """Serialize manifest to canonical JSON."""
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()


def _serialize(rel: AgentRelease) -> dict:
    """Serialize AgentRelease to dict for JSON response."""
    result = {
        "id": str(rel.id),
        "version": rel.version,
        "channel": rel.channel.value if hasattr(rel.channel, "value") else rel.channel,
        "os": rel.os,
        "arch": rel.arch,
        "sha256": rel.sha256,
        "size": rel.size,
        "status": rel.status.value if hasattr(rel.status, "value") else rel.status,
        "manifest_json": rel.manifest_json.decode(),
        "manifest_sig_hex": rel.manifest_sig.hex(),
        "uploaded_at": rel.uploaded_at.isoformat(),
        "uploaded_by": rel.uploaded_by,
    }
    if rel.yanked_at:
        result["yanked_at"] = rel.yanked_at.isoformat()
    if rel.yanked_reason:
        result["yanked_reason"] = rel.yanked_reason
    return result


def make_download_token(release_id: uuid.UUID | str, host_id: uuid.UUID | str) -> str:
    """Create a download token for a release.

    Token is HS256 JWT with (rid, hid, exp) claims. TTL: 10 minutes.
    """
    payload = {
        "rid": str(release_id),
        "hid": str(host_id),
        "exp": datetime.now(timezone.utc) + DOWNLOAD_TOKEN_TTL,
    }
    return jwt.encode(payload, _get_session_secret(), algorithm="HS256")


def _require_ci_auth(authorization: str | None = Header(None)) -> str:
    """Dependency: validate Bearer token matches HL_CI_TOKEN env var."""
    expected = os.environ.get("HL_CI_TOKEN", "")
    if not expected:
        raise HTTPException(503, "CI auth not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    presented = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(403, "invalid CI token")
    return "ci"


@router.post("", status_code=201)
async def upload_release(
    req: Request,
    binary: UploadFile = File(...),
    version: str = Form(...),
    channel: ReleaseChannel = Form(...),
    os_: str = Form(..., alias="os"),
    arch: str = Form(...),
    min_prev_version: str | None = Form(None),
    _ci_auth=Depends(_require_ci_auth),
):
    """Upload a new agent release.

    Accepts multipart: binary + metadata (version, channel, os, arch, min_prev_version).
    Computes SHA256, signs manifest with CA, persists row, writes binary to disk.
    Requires CI auth via HL_CI_TOKEN env var.
    """
    app_state = get_app_state(req)

    data = await binary.read()
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)

    # Write binary to disk
    target = _binary_path(version, os_, arch)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o644)

    # Build manifest
    manifest = {
        "version": version,
        "channel": channel.value,
        "os": os_,
        "arch": arch,
        "sha256": sha,
        "size": size,
        "released_at": datetime.now(timezone.utc).isoformat(),
        "min_prev_version": min_prev_version or "",
    }
    manifest_json = _make_manifest(manifest)
    sig = app_state.ca.sign_release_manifest(manifest_json)

    # Persist to DB
    async with app_state.sessionmaker() as session:
        rel = AgentRelease(
            version=version,
            channel=channel,
            os=os_,
            arch=arch,
            sha256=sha,
            size=size,
            manifest_json=manifest_json,
            manifest_sig=sig,
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="ci",
        )
        session.add(rel)
        await session.commit()
        # Refresh to get the ID and other auto-generated fields
        await session.refresh(rel)
        return _serialize(rel)


@router.get("")
async def list_releases(
    req: Request,
    channel: ReleaseChannel | None = Query(None),
    os_: str | None = Query(None, alias="os"),
    arch: str | None = Query(None),
    status_: ReleaseStatus | None = Query(None, alias="status"),
):
    """List releases with optional filters.

    Query params: channel, os, arch, status. Returns paginated list ordered by uploaded_at desc.
    """
    app_state = get_app_state(req)

    async with app_state.sessionmaker() as session:
        stmt = select(AgentRelease)
        if channel:
            stmt = stmt.where(AgentRelease.channel == channel)
        if os_:
            stmt = stmt.where(AgentRelease.os == os_)
        if arch:
            stmt = stmt.where(AgentRelease.arch == arch)
        if status_:
            stmt = stmt.where(AgentRelease.status == status_)
        stmt = stmt.order_by(AgentRelease.uploaded_at.desc())
        rows = (await session.execute(stmt)).scalars().all()

    return {"items": [_serialize(r) for r in rows]}


@router.get("/latest")
async def latest_release(
    req: Request,
    channel: ReleaseChannel = Query(ReleaseChannel.STABLE),
    os_: str = Query(..., alias="os"),
    arch: str = Query(...),
):
    """Get newest published release for a platform.

    Query params: channel, os (required), arch (required).
    Returns 404 if no published release exists.
    """
    app_state = get_app_state(req)

    async with app_state.sessionmaker() as session:
        stmt = (
            select(AgentRelease)
            .where(
                AgentRelease.channel == channel,
                AgentRelease.os == os_,
                AgentRelease.arch == arch,
                AgentRelease.status == ReleaseStatus.PUBLISHED,
            )
            .order_by(AgentRelease.uploaded_at.desc())
            .limit(1)
        )
        rel = (await session.execute(stmt)).scalar_one_or_none()

    if not rel:
        raise HTTPException(404, "no published release")
    return _serialize(rel)


@router.get("/{rid}/manifest")
async def get_manifest(
    req: Request,
    rid: str,
):
    """Get signed manifest for a release.

    Returns manifest_json (canonical JSON) and manifest_sig_hex (Ed25519 signature).
    Returns 404 if release not found or yanked.
    """
    app_state = get_app_state(req)

    async with app_state.sessionmaker() as session:
        rel = await session.get(AgentRelease, rid)

    if not rel or rel.status == ReleaseStatus.YANKED:
        raise HTTPException(404)

    return {
        "manifest_json": rel.manifest_json.decode(),
        "manifest_sig_hex": rel.manifest_sig.hex(),
    }


@router.get("/{rid}/binary")
async def download_binary(
    req: Request,
    rid: str,
    token: str = Query(...),
):
    """Stream binary for a release.

    Requires token query param (JWT with rid, hid, exp).
    Returns 401 if token invalid/mismatch, 404 if release/binary missing.
    """
    app_state = get_app_state(req)

    # Validate token
    try:
        claims = jwt.decode(token, _get_session_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid download token")

    if claims.get("rid") != rid:
        raise HTTPException(401, "token release mismatch")

    async with app_state.sessionmaker() as session:
        rel = await session.get(AgentRelease, rid)

    if not rel or rel.status == ReleaseStatus.YANKED:
        raise HTTPException(404)

    path = _binary_path(rel.version, rel.os, rel.arch)
    if not path.exists():
        raise HTTPException(410, "binary missing")

    def _iter():
        with path.open("rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type="application/octet-stream",
        headers={"X-SHA256": rel.sha256, "Content-Length": str(rel.size)},
    )


@router.post("/{rid}/yank")
async def yank_release(
    req: Request,
    rid: str,
    body: dict,
    admin=Depends(admin_required),
):
    """Mark a release as yanked.

    Requires admin auth. Sets status=yanked, yanked_at, yanked_reason.
    Returns 404 if release not found.
    """
    app_state = get_app_state(req)

    async with app_state.sessionmaker() as session:
        rel = await session.get(AgentRelease, rid)
        if not rel:
            raise HTTPException(404)

        rel.status = ReleaseStatus.YANKED
        rel.yanked_at = datetime.now(timezone.utc)
        rel.yanked_reason = body.get("reason", "")
        await session.commit()
        return _serialize(rel)
