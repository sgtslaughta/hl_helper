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
from typing import Any, Awaitable, Callable

import structlog
from fastapi import Depends, HTTPException, Request

from server.app.deps import current_principal as default_principal_dep
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

        # Fix 2: Defensive sessionmaker check
        sm = getattr(request.app.state, "sessionmaker", None)
        if sm is None:
            raise HTTPException(status_code=500, detail="rbac_session_unavailable")

        async with sm() as session:
            engine = BuiltinEngine(session)
            decision = await engine.is_authorized(
                principal, action, resource, AuthContext.empty()
            )

        if not decision.allow:
            audit = getattr(request.app.state, "audit_chain", None)
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
