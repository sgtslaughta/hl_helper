"""API routes for role bindings."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models.binding import Binding
from server.app.models.role import Role

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/bindings", tags=["bindings"])


def compute_scope_hash(kind: str, value: dict[str, object]) -> str:
    """Compute scope_hash from kind and value."""
    canon = json.dumps({"kind": kind, "value": value}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def _validate_scope_value(kind: str, value: dict[str, object]) -> None:
    """Validate scope_value shape matches scope_kind.

    Raises HTTPException with 422 if invalid.
    """
    if kind == "global":
        if value != {}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="global_scope_takes_no_value",
            )
        return
    if kind == "group":
        gid = value.get("group_id")
        if not isinstance(gid, str) or not gid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="group_scope_requires_nonempty_group_id",
            )
        return
    if kind == "tag":
        k = value.get("key")
        v = value.get("value")
        if not isinstance(k, str) or not k or not isinstance(v, str) or not v:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="tag_scope_requires_nonempty_key_and_value",
            )
        return
    if kind == "host_list":
        ids = value.get("host_ids")
        if not isinstance(ids, list) or not ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="host_list_requires_nonempty_array",
            )
        if not all(isinstance(x, str) and x for x in ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="host_list_ids_must_be_nonempty_strings",
            )
        return
    if kind == "self":
        pid = value.get("principal_id", "")
        if not isinstance(pid, str) or not pid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="self_scope_requires_nonempty_principal_id",
            )
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"unknown_scope_kind: {kind}",
    )


# Pydantic models
class BindingCreate(BaseModel):
    """Request to create a binding."""

    principal_type: Literal["user", "user_group", "service_account"] = Field(
        ..., description="user | user_group | service_account"
    )
    principal_id: str = Field(..., description="ID of the principal subject")
    role_id: str = Field(..., description="UUID of the Role being bound")
    scope_kind: Literal["global", "group", "tag", "host_list", "self"] = Field(
        ..., description="global | group | tag | host_list | self"
    )
    scope_value: dict[str, object] = Field(
        ..., description="Shape per scope_kind; see /docs"
    )


class BindingOut(BaseModel):
    """Response with binding details."""

    id: str
    principal_type: str
    principal_id: str
    role_id: str
    scope_kind: str
    scope_value: dict[str, object]
    scope_hash: str
    created_at: datetime


@router.get(
    "",
    response_model=list[BindingOut],
    dependencies=[Depends(admin_required)],
)
async def list_bindings(
    req: Request,
    principal_id: str | None = None,
    role_id: str | None = None,
) -> list[BindingOut]:
    """List bindings with optional filters.

    Requires admin authentication.

    Query params:
    - principal_id: filter by principal_id
    - role_id: filter by role_id
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        query = select(Binding)
        if principal_id:
            query = query.where(Binding.principal_id == principal_id)
        if role_id:
            query = query.where(Binding.role_id == role_id)

        result = await session.execute(query)
        bindings = result.scalars().all()

    return [
        BindingOut(
            id=b.id,
            principal_type=b.principal_type.value,
            principal_id=b.principal_id,
            role_id=b.role_id,
            scope_kind=b.scope_kind.value,
            scope_value=b.scope_value,
            scope_hash=b.scope_hash,
            created_at=b.created_at,
        )
        for b in bindings
    ]


@router.get(
    "/{binding_id}",
    response_model=BindingOut,
    dependencies=[Depends(admin_required)],
)
async def get_binding(req: Request, binding_id: str) -> BindingOut:
    """Get binding by ID.

    Requires admin authentication.
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        binding = await session.scalar(
            select(Binding).where(Binding.id == binding_id)
        )
        if not binding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Binding not found",
            )

    return BindingOut(
        id=binding.id,
        principal_type=binding.principal_type.value,
        principal_id=binding.principal_id,
        role_id=binding.role_id,
        scope_kind=binding.scope_kind.value,
        scope_value=binding.scope_value,
        scope_hash=binding.scope_hash,
        created_at=binding.created_at,
    )


@router.post(
    "",
    response_model=BindingOut,
    status_code=201,
    dependencies=[Depends(admin_required)],
)
async def create_binding(req: Request, body: BindingCreate) -> BindingOut:
    """Create a binding.

    Requires admin authentication.

    Server computes scope_hash; rejects duplicate (principal_type, principal_id, role_id, scope_hash)
    with 409.
    """
    # Validate scope_value shape
    _validate_scope_value(body.scope_kind, body.scope_value)

    # Compute scope_hash
    scope_hash = compute_scope_hash(body.scope_kind, body.scope_value)

    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        # Verify role_id exists
        role = await session.scalar(select(Role).where(Role.id == body.role_id))
        if not role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Role not found",
            )

        # Create binding
        binding = Binding(
            principal_type=body.principal_type,
            principal_id=body.principal_id,
            role_id=body.role_id,
            scope_kind=body.scope_kind,
            scope_value=body.scope_value,
            scope_hash=scope_hash,
        )
        session.add(binding)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="duplicate_binding",
            ) from None

        await session.refresh(binding)

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="binding.created",
                    subject=binding.id,
                    payload={
                        "principal_type": binding.principal_type.value,
                        "principal_id": binding.principal_id,
                        "role_id": binding.role_id,
                        "scope_kind": binding.scope_kind.value,
                    },
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)

        # Publish rbac.binding_changed for cache + session invalidation
        try:
            await app_state.bus.publish(
                "rbac.binding_changed",
                {
                    "binding_id": binding.id,
                    "principal_type": binding.principal_type.value,
                    "principal_id": binding.principal_id,
                    "user_id": binding.principal_id if binding.principal_type.value == "user" else None,
                    "role_id": binding.role_id,
                    "op": "created",
                },
            )
        except Exception as e:
            log.exception("bus_publish_failed", exc=e)

    return BindingOut(
        id=binding.id,
        principal_type=binding.principal_type.value,
        principal_id=binding.principal_id,
        role_id=binding.role_id,
        scope_kind=binding.scope_kind.value,
        scope_value=binding.scope_value,
        scope_hash=binding.scope_hash,
        created_at=binding.created_at,
    )


@router.delete(
    "/{binding_id}",
    status_code=204,
    dependencies=[Depends(admin_required)],
)
async def delete_binding(req: Request, binding_id: str) -> None:
    """Delete a binding.

    Requires admin authentication.
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        binding = await session.scalar(
            select(Binding).where(Binding.id == binding_id)
        )
        if not binding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Binding not found",
            )

        principal_type = binding.principal_type.value
        principal_id = binding.principal_id
        role_id = binding.role_id
        binding_id = binding.id
        await session.delete(binding)
        await session.commit()

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="binding.deleted",
                    subject=binding_id,
                    payload={
                        "principal_type": principal_type,
                        "principal_id": principal_id,
                        "role_id": role_id,
                    },
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)

        try:
            await app_state.bus.publish(
                "rbac.binding_changed",
                {
                    "binding_id": binding_id,
                    "principal_type": principal_type,
                    "principal_id": principal_id,
                    "user_id": principal_id if principal_type == "user" else None,
                    "role_id": role_id,
                    "op": "deleted",
                },
            )
        except Exception as e:
            log.exception("bus_publish_failed", exc=e)
