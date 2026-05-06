"""Serve hl-agent binaries for installer download."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["agent-dist"])


# Allowed arch slugs map to filenames in the dist dir.
# The Go Makefile produces a single binary at agent/bin/hl-agent for the
# current arch; for multi-arch dist set HL_AGENT_DIST_DIR with one binary per
# arch named hl-agent-<arch>.
_ALLOWED_ARCHES = {"amd64", "arm64", "armv7"}


def _dist_dir() -> Path:
    """Resolve the agent binary dist directory.

    Honors HL_AGENT_DIST_DIR override; otherwise points at agent/bin alongside
    the repo (dev) so a freshly built `make -C agent build` is served as-is.
    """
    override = os.environ.get("HL_AGENT_DIST_DIR")
    if override:
        return Path(override)
    # Fall back to repo-relative agent/bin from server package location:
    # server/app/api/v1/agent_dist.py -> repo root is parents[4].
    return Path(__file__).resolve().parents[4] / "agent" / "bin"


@router.get("/agent/{arch}/hl-agent")
async def get_agent_binary(arch: str) -> FileResponse:
    """Return the hl-agent binary for the given arch.

    Looks for `hl-agent-<arch>` first; falls back to `hl-agent` (single-arch
    dev build) when the arch-suffixed binary is absent. 404s if neither exists.
    """
    if arch not in _ALLOWED_ARCHES:
        raise HTTPException(status_code=400, detail=f"unsupported arch: {arch}")
    base = _dist_dir()
    candidate = base / f"hl-agent-{arch}"
    if not candidate.exists():
        # dev fallback: single binary at hl-agent
        fallback = base / "hl-agent"
        if fallback.exists():
            candidate = fallback
        else:
            raise HTTPException(status_code=404, detail="agent binary not found")
    return FileResponse(
        candidate,
        media_type="application/octet-stream",
        filename="hl-agent",
    )
