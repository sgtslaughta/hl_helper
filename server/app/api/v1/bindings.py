"""API routes for role bindings."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.api.middleware.admin_auth import admin_required
from server.app.models.binding import Binding
from server.app.models.role import Role

router = APIRouter(prefix="/v1/bindings", tags=["bindings"])


def _compute_scope_hash(kind: str, value: dict[str, object]) -> str:
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="global scope must have empty value",
            )
    elif kind == "group":
        if "group_id" not in value or not isinstance(value.get("group_id"), str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="group scope must have group_id: str",
            )
    elif kind == "tag":
        if "key" not in value or "value" not in value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tag scope must have key: str and value: str",
            )
        if not isinstance(value.get("key"), str) or not isinstance(value.get("value"), str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tag scope must have key: str and value: str",
            )
    elif kind == "host_list":
        if "host_ids" not in value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="host_list scope must have host_ids: [str]",
            )
        if not isinstance(value.get("host_ids"), list):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="host_list scope must have host_ids: [str]",
            )
    elif kind == "self":
        # self can have {"principal_id": str} or {}
        if value and "principal_id" in value:
            if not isinstance(value.get("principal_id"), str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="self scope principal_id must be str",
                )


# Pydantic models
class BindingCreate(BaseModel):
    """Request to create a binding."""

    principal_type: Literal["user", "user_group", "service_account"]
    principal_id: str
    role_id: str
    scope_kind: Literal["global", "group", "tag", "host_list", "self"]
    scope_value: dict[str, object]


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
    sm = req.app.state.sessionmaker
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
    sm = req.app.state.sessionmaker
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
    scope_hash = _compute_scope_hash(body.scope_kind, body.scope_value)

    sm = req.app.state.sessionmaker
    async with sm() as session:
        # Verify role_id exists
        role = await session.scalar(select(Role).where(Role.id == body.role_id))
        if not role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                detail="Binding with this principal, role, and scope already exists",
            )

        await session.refresh(binding)

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
    sm = req.app.state.sessionmaker
    async with sm() as session:
        binding = await session.scalar(
            select(Binding).where(Binding.id == binding_id)
        )
        if not binding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Binding not found",
            )

        await session.delete(binding)
        await session.commit()
