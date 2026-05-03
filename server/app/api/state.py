"""Helper to resolve AppState from a FastAPI request.

Lives in its own module to avoid circular imports between app.py (which
includes v1 routers) and v1 routers (which need AppState).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import Request


def get_app_state(request: Request) -> Any:
    """Return AppState from app.state.app_state, or a SimpleNamespace shim.

    In production, lifespan stores AppState at app.state.app_state.
    In tests that inject state attributes directly (legacy path), fall back
    to synthesizing from individual attributes via a SimpleNamespace.
    """
    state = getattr(request.app.state, "app_state", None)
    if state is not None:
        return state
    return SimpleNamespace(
        sessionmaker=getattr(request.app.state, "sessionmaker", None),
        audit_chain=getattr(request.app.state, "audit_chain", None),
        dispatcher=getattr(request.app.state, "dispatcher", None),
        api_dispatcher=getattr(request.app.state, "api_dispatcher", None),
        signing_backend=getattr(request.app.state, "signing_backend", None),
        enrollment_service=getattr(request.app.state, "enrollment_service", None),
        revocation_service=getattr(request.app.state, "revocation_service", None),
        ca=getattr(request.app.state, "ca", None),
        engine=getattr(request.app.state, "engine", None),
    )
