"""Admin authentication middleware."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from server.app.settings.config import load_settings


async def admin_required(request: Request) -> str:
    """Dependency to verify admin Bearer token.

    Verifies Authorization: Bearer <token> header against settings.admin_token.
    If token unset → 503 (server misconfigured).
    If wrong token → 401 (unauthorized).

    Returns:
        "admin" actor string if valid
    """
    settings = load_settings()

    # Check if admin_token is configured
    if settings.admin_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not configured with admin token",
        )

    # Extract Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header[7:]  # Strip "Bearer " prefix

    # Verify token
    if token != settings.admin_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )

    return "admin"
