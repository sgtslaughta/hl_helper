"""FastAPI RBAC dependency factory.

Usage:
    @router.post("/v1/hosts/{id}/actions/reboot",
                 dependencies=[Depends(require("host:reboot", host_resource))])
    async def reboot(...): ...

`resource_loader` may be sync or async. If omitted, GlobalResource() is used
(only `global` scope can authorize).

Note: _build_principal is deferred until C3 ships real auth. Until then, only
Principal instances are accepted; dict/JWT claims yield 401.
"""

from __future__ import annotations

import inspect as _inspect
from typing import Annotated, Any, Awaitable, Callable

import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from server.app.deps import current_principal as default_principal_dep
from server.app.models.user import User
from server.app.models.user_group import UserGroup, user_group_members
from server.app.rbac import (
    AuthContext,
    BuiltinEngine,
    Decision,
    GlobalResource,
    Principal,
    Resource,
)

ResourceLoader = Callable[[Request], Resource | Awaitable[Resource]]


def _build_principal(raw: object | None) -> Principal | None:
    """Map current_principal output to a Principal. None until C3 ships real auth."""
    if raw is None:
        return None
    if isinstance(raw, Principal):
        return raw
    return None


async def _resolve_resource(loader: ResourceLoader | None, req: Request) -> Resource:
    if loader is None:
        return GlobalResource().as_resource
    res = loader(req)
    if _inspect.isawaitable(res):
        res = await res
    return res


def require(
    action: str, resource_loader: ResourceLoader | None = None
) -> Any:
    """Build a FastAPI dependency that authorizes `action` against `resource_loader`.

    Behavior:
      - Returns the granting Decision on success (callers can read `decision.binding_id`).
      - Raises HTTP 401 if no principal.
      - Raises HTTP 403 + emits audit entry on deny.
    """

    async def _dep(
        request: Request,
        raw_principal: object | None = Depends(default_principal_dep),
    ) -> Decision:
        principal = _build_principal(raw_principal)
        if principal is None:
            raise HTTPException(status_code=401, detail="unauthenticated")

        resource = await _resolve_resource(resource_loader, request)

        # Defensive sessionmaker check. Read from AppState (production lifespan)
        # or fall back to direct app.state.sessionmaker injection (legacy tests).
        sm = getattr(request.app.state, "sessionmaker", None)
        if sm is None:
            app_state = getattr(request.app.state, "app_state", None)
            sm = getattr(app_state, "sessionmaker", None) if app_state else None
        if sm is None:
            raise HTTPException(status_code=500, detail="rbac_session_unavailable")

        async with sm() as session:
            engine = BuiltinEngine(session)
            decision = await engine.is_authorized(
                principal, action, resource, AuthContext.empty()
            )

        if not decision.allow:
            audit = getattr(request.app.state, "audit_chain", None)
            if audit is None:
                app_state = getattr(request.app.state, "app_state", None)
                audit = getattr(app_state, "audit_chain", None) if app_state else None
            if audit is not None:
                principal_id = principal.user_id or principal.service_account_id or "<unknown>"
                async with sm() as audit_session:
                    try:
                        await audit.append(
                            audit_session,
                            actor=principal_id,
                            action="rbac.denied",
                            subject=getattr(resource, "id", None),
                            payload={"perm": action, "reason": decision.reason},
                        )
                        await audit_session.commit()
                    except Exception as e:
                        # Fix 1: Wrap audit.append in try/except so failure doesn't mask 403
                        structlog.get_logger().exception("audit_chain_failed", exc=e)
            raise HTTPException(
                status_code=403,
                detail=f"permission_denied: action={action}",
            )
        return decision

    return _dep


async def lookup_principal(sm: Any, user_id: str) -> Principal:
    """Look up a user and build a Principal from their roles and groups.

    Args:
        sm: Async sessionmaker for database access.
        user_id: User ID to look up.

    Returns:
        Principal with user_id, user_group_ids populated from DB.

    Raises:
        HTTPException(404) if user not found.
    """
    async with sm() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")

        # Get user's groups
        group_query = select(UserGroup.id).select_from(UserGroup).join(
            user_group_members,
            user_group_members.c.user_group_id == UserGroup.id,
        ).where(user_group_members.c.user_id == user_id)

        groups_result = await session.execute(group_query)
        group_ids = [str(gid) for gid in groups_result.scalars().all()]

    return Principal(user_id=user_id, user_group_ids=frozenset(group_ids))


async def acting_principal(
    request: Request,
    current: Annotated[Principal | None, Depends(default_principal_dep)],
) -> Principal:
    """Extract and validate X-Acting-Principal header against current principal.

    Behavior:
    1. If header missing → return `current` (or 401 if None).
    2. If header == current.user_id → return `current`.
    3. Otherwise:
       - Check if `current` has `user:impersonate` permission.
       - If yes: look up the spoofed user, build Principal, return it.
       - If no: raise 403 "impersonation forbidden".
       - If spoofed user doesn't exist: raise 404.

    Args:
        request: FastAPI request.
        current: Authenticated principal from current_principal dependency.

    Returns:
        Principal to use for the request (authenticated or spoofed).

    Raises:
        HTTPException(401) if no authenticated principal and no header.
        HTTPException(403) if impersonation not permitted.
        HTTPException(404) if spoofed user not found.
    """
    # Get the header value
    header_value = request.headers.get("X-Acting-Principal", "").strip()

    # Case 1: No header → use current (or 401)
    if not header_value:
        if current is None:
            raise HTTPException(status_code=401, detail="unauthenticated")
        return current

    # Case 2: Header matches current user_id → return current
    if current is not None and header_value == current.user_id:
        return current

    # Case 3: Header differs from current → check impersonate permission
    if current is None:
        raise HTTPException(status_code=401, detail="unauthenticated")

    # Get sessionmaker from app state
    sm = getattr(request.app.state, "sessionmaker", None)
    if sm is None:
        app_state = getattr(request.app.state, "app_state", None)
        sm = getattr(app_state, "sessionmaker", None) if app_state else None
    if sm is None:
        raise HTTPException(status_code=500, detail="rbac_session_unavailable")

    # Check if current principal has user:impersonate permission
    async with sm() as session:
        engine = BuiltinEngine(session)
        decision = await engine.is_authorized(
            current, "user:impersonate", GlobalResource().as_resource, AuthContext.empty()
        )

    if not decision.allow:
        raise HTTPException(status_code=403, detail="impersonation_forbidden")

    # Look up the spoofed user (will raise 404 if not found)
    spoofed = await lookup_principal(sm, header_value)
    return spoofed
