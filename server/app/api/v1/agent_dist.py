"""Serve hl-agent binaries for installer download.

Legacy compatibility shim. New install scripts should use
`/v1/install/agent-binary?token=...` directly. The legacy `/agent/{arch}/hl-agent`
route now requires a live enrollment token query param to prevent anonymous
binary enumeration.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from server.app.api.state import get_app_state
from server.app.api.v1.install import _validate_enrollment_token

router = APIRouter(tags=["agent-dist"])

_ALLOWED_ARCHES = {"amd64", "arm64", "armv7"}


@router.get("/agent/{arch}/hl-agent", deprecated=True)
async def get_agent_binary(
    request: Request,
    arch: str,
    token: str = Query(..., description="enrollment token (required)"),
) -> RedirectResponse:
    """Legacy install path — redirects to the token-gated bootstrap endpoint.

    Old `curl ... | sh` scripts still hit `/agent/{arch}/hl-agent`. Rather
    than serving binaries unauthenticated, validate the enrollment token
    and redirect to `/v1/install/agent-binary` which performs the same
    validation + serves from the signed-manifest registry.
    """
    if arch not in _ALLOWED_ARCHES:
        raise HTTPException(status_code=400, detail=f"unsupported arch: {arch}")
    # Auth gate (raises 401 on bad token); we reuse the same token after
    # the redirect so the bootstrap endpoint validates it again.
    app_state = get_app_state(request)
    async with app_state.sessionmaker() as session:
        await _validate_enrollment_token(token, session)
    return RedirectResponse(
        url=f"/v1/install/agent-binary?token={token}&os=linux&arch={arch}",
        status_code=307,
    )


@router.get("/agent/{arch}/latest", deprecated=True)
async def latest_agent(arch: str) -> RedirectResponse:
    """Redirect to /v1/agent-releases/latest with os and arch params.

    This endpoint is deprecated. Use /v1/agent-releases/latest instead.
    """
    if arch not in _ALLOWED_ARCHES:
        raise HTTPException(status_code=400, detail=f"unsupported arch: {arch}")
    return RedirectResponse(url=f"/v1/agent-releases/latest?os=linux&arch={arch}")
