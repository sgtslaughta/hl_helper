"""Admin authentication middleware.

Accepts either:
1. Authorization: Bearer <admin_token> -- automation / out-of-band ops.
2. hls_session cookie owned by a user with admin or owner role -- web UI.

A 401 is returned only when neither path produces a valid principal. Authed
users without elevated roles get 403 so the frontend can distinguish session
expiry (401 → redirect to login) from missing permissions (403 → show 'no
access' UI without bouncing the session).
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from server.app.deps import current_principal
from server.app.settings.config import load_settings

_ADMIN_ROLES = frozenset({"admin", "owner"})


async def admin_required(request: Request) -> str:
    """Dependency: admin via Bearer token OR session cookie with admin/owner role."""
    settings = load_settings()

    if settings.admin_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not configured with admin token",
        )

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if secrets.compare_digest(token, settings.admin_token.get_secret_value()):
            request.state.admin_authenticated = True
            return "admin"
        # Fall through to session-cookie attempt; if both fail, 401 below.

    # Session-cookie path: derive principal, then ensure it carries admin or owner role.
    try:
        principal = await current_principal(request)
    except HTTPException:
        # current_principal can raise 403 on CSRF mismatch; surface that directly.
        raise
    except Exception:
        principal = None

    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    roles = await _user_roles(request, principal.user_id)
    if not (_ADMIN_ROLES & roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )

    request.state.admin_authenticated = True
    return f"user:{principal.user_id}"


async def _user_roles(request: Request, user_id: str | None) -> set[str]:
    """Return role names granted to user_id via direct + group bindings.

    Best-effort: missing tables or query errors yield an empty set so the
    surrounding 403 path stays consistent.
    """
    if not user_id:
        return set()
    try:
        from sqlalchemy import select

        from server.app.api.state import get_app_state
        from server.app.models.binding import Binding
        from server.app.models.role import Role

        app_state = get_app_state(request)
        async with app_state.sessionmaker() as session:
            stmt = (
                select(Role.name)
                .join(Binding, Binding.role_id == Role.id)
                .where(Binding.principal_type == "user", Binding.principal_id == user_id)
            )
            return set((await session.execute(stmt)).scalars().all())
    except Exception:
        return set()
