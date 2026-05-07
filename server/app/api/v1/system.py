"""System-level admin endpoints (server-side network info, etc.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/advertised-origins", dependencies=[Depends(admin_required)])
async def advertised_origins(request: Request) -> dict[str, object]:
    """Return the list of `https://IP:PORT` origins this server advertises
    for enrollment install commands, plus the configured default.

    Used by the enrollment-mint flow on a multi-homed server: the operator
    picks which IP install commands target so agents on other subnets reach
    a routable address instead of the loopback the server bound to.
    """
    state = get_app_state(request)
    origins = list(getattr(state, "advertised_origins", None) or [])
    default = getattr(state, "public_origin", None) or (origins[0] if origins else "")
    return {"origins": origins, "default": default}
