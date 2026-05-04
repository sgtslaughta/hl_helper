"""Common FastAPI dependencies. Auth principal extraction via sessions + API keys."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from server.app.api.state import get_app_state
from server.app.auth.sessions import make_request_meta
from server.app.auth.transports import extract_token
from server.app.rbac.provider import Principal


async def current_principal(request: Request) -> Principal | None:
    """Extract principal from session or API key.

    Tries in order:
    1. Authorization: Bearer hls_... header (session token)
    2. hls_session cookie (session token)
    3. API key (existing path, delegated to get_app_state logic)

    For cookie-based auth on state-changing methods (POST, PUT, PATCH, DELETE),
    requires X-CSRF-Token header matching hls_csrf cookie. Bearer path skips CSRF.

    Returns:
        Principal if authenticated; None otherwise.

    Raises:
        HTTPException: 403 if cookie path and CSRF validation fails.
    """
    # Try to get app_state; if not available, return None
    try:
        app_state = get_app_state(request)
    except RuntimeError:
        # AppState not initialized; no session available
        return None

    # Extract token using transports helper
    token, source = extract_token(request)

    if token and app_state.session_service:
        # Check CSRF for cookie-based auth on state-changing methods
        if source == "cookie" and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf_cookie = request.cookies.get("hls_csrf")
            csrf_header = request.headers.get("X-CSRF-Token")
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token mismatch")

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

    # No session found, return None (downstream auth gates handle)
    return None
