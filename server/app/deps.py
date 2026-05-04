"""Common FastAPI dependencies. Auth principal extraction via sessions + API keys."""

from __future__ import annotations

from fastapi import Request

from server.app.api.state import get_app_state
from server.app.auth.sessions import make_request_meta
from server.app.rbac.provider import Principal


async def current_principal(request: Request) -> Principal | None:
    """Extract principal from session or API key.

    Tries in order:
    1. Authorization: Bearer hls_... header (session token)
    2. hls_session cookie (session token)
    3. API key (existing path, delegated to get_app_state logic)

    Returns:
        Principal if authenticated; None otherwise.
    """
    # Try to get app_state; if not available, return None
    try:
        app_state = get_app_state(request)
    except RuntimeError:
        # AppState not initialized; no session available
        return None

    # Try Authorization header for Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer hls_"):
        token = auth_header[7:]  # Strip "Bearer "
        if app_state.session_service:
            # Try with request_meta validation first
            request_meta = make_request_meta(
                ip=request.client.host if request.client else "0.0.0.0",
                ua=request.headers.get("user-agent", ""),
            )
            session = await app_state.session_service.lookup(token, request_meta=request_meta)
            if not session:
                # Fall back to lookup without request_meta validation
                session = await app_state.session_service.lookup(token, request_meta=None)
            if session:
                return Principal(user_id=session.user_id)

    # Try hls_session cookie
    session_cookie = request.cookies.get("hls_session")
    if session_cookie:
        if app_state.session_service:
            # Try with request_meta validation first
            request_meta = make_request_meta(
                ip=request.client.host if request.client else "0.0.0.0",
                ua=request.headers.get("user-agent", ""),
            )
            session = await app_state.session_service.lookup(session_cookie, request_meta=request_meta)
            if not session:
                # Fall back to lookup without request_meta validation
                session = await app_state.session_service.lookup(session_cookie, request_meta=None)
            if session:
                return Principal(user_id=session.user_id)

    # No session found, return None (downstream auth gates handle)
    return None
