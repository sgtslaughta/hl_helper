"""Roles API: CRUD for custom roles, read-only access to built-in roles.

Built-in roles (viewer, operator, admin, owner) are immutable.
Custom roles can be created, updated, and deleted.
All permission strings are validated against the Catalog.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models import Role, Binding
from server.app.rbac.catalog import Catalog

router = APIRouter(prefix="/v1/roles", tags=["roles"])
log = structlog.get_logger(__name__)


class RoleCreate(BaseModel):
    """Request to create a new custom role."""
    name: str = Field(..., description="Role name (unique)")
    description: str | None = Field(None, description="Role description")
    permissions: list[str] = Field(..., description="List of permission strings")


class RoleUpdate(BaseModel):
    """Request to update a custom role."""
    description: str | None = Field(None, description="New description")
    permissions: list[str] | None = Field(None, description="New permissions list")


class RoleOut(BaseModel):
    """Role response with all fields."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Role ID")
    name: str = Field(..., description="Role name")
    description: str | None = Field(None, description="Role description")
    built_in: bool = Field(..., description="Whether this is a built-in role")
    permissions: list[str] = Field(..., description="List of permission strings")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Last updated timestamp")


def _get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    """Extract sessionmaker from app state."""
    return get_app_state(request).sessionmaker


def _validate_permissions(perms: list[str]) -> None:
    """Validate permission strings against Catalog.

    Raises:
        HTTPException(422) if any permission is invalid.
    """
    catalog = Catalog.load()
    valid_perms = catalog.permissions
    invalid = [p for p in perms if p not in valid_perms]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid permissions: {', '.join(sorted(invalid))}",
        )


@router.get("", response_model=list[RoleOut])
async def list_roles(
    request: Request,
    actor: str = Depends(admin_required),
    sm: Any = Depends(_get_sessionmaker),
) -> list[RoleOut]:
    """List all roles (admin-gated).

    Returns:
        List of all roles with built_in flag.
    """
    async with sm() as session:
        rows = (await session.execute(select(Role).order_by(Role.name))).scalars().all()
        return [RoleOut.model_validate(r) for r in rows]


@router.get("/{role_id}", response_model=RoleOut)
async def get_role(
    role_id: str,
    request: Request,
    actor: str = Depends(admin_required),
    sm: Any = Depends(_get_sessionmaker),
) -> RoleOut:
    """Get a single role by ID (admin-gated)."""
    async with sm() as session:
        role = await session.get(Role, role_id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role {role_id} not found",
            )
        return RoleOut.model_validate(role)


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    request: Request,
    actor: str = Depends(admin_required),
    sm: Any = Depends(_get_sessionmaker),
) -> RoleOut:
    """Create a new custom role.

    Args:
        body: Role creation request (name, description?, permissions[])

    Returns:
        Created role with 201 status.

    Raises:
        422: If any permission not in Catalog.
    """
    _validate_permissions(body.permissions)

    role = Role(
        name=body.name,
        description=body.description,
        built_in=False,
        permissions=body.permissions,
    )

    async with sm() as session:
        session.add(role)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="role_name_conflict",
            ) from None

        await session.refresh(role)
        # TODO(T2.4): bump engine perm-cache version on role mutate
        # TODO: emit audit event action="role.created" if audit chain available
        return RoleOut.model_validate(role)


@router.patch("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: str,
    body: RoleUpdate,
    request: Request,
    actor: str = Depends(admin_required),
    sm: Any = Depends(_get_sessionmaker),
) -> RoleOut:
    """Update a custom role (PATCH).

    Only custom roles can be updated. Built-in roles reject with 403.
    Empty permissions list is valid (creates an inert role with no permissions).

    Args:
        role_id: Role to update
        body: Fields to update (description?, permissions?)
              - description: None clears the field; string sets it
              - permissions: empty list is valid; None leaves unchanged

    Returns:
        Updated role.

    Raises:
        403: If role.built_in is True.
        404: If role not found.
        422: If any permission not in Catalog.
    """
    async with sm() as session:
        role = await session.get(Role, role_id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role {role_id} not found",
            )

        # Reject updates to built-in roles
        if role.built_in:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify built-in roles",
            )

        # Update only fields that were explicitly set in the request
        data = body.model_dump(exclude_unset=True)

        if "description" in data:
            role.description = data["description"]

        if "permissions" in data and data["permissions"] is not None:
            _validate_permissions(data["permissions"])
            role.permissions = data["permissions"]

        await session.commit()
        # TODO(T2.4): bump engine perm-cache version on role mutate
        # TODO: emit audit event action="role.updated" if audit chain available
        await session.refresh(role)
        return RoleOut.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: str,
    request: Request,
    actor: str = Depends(admin_required),
    sm: Any = Depends(_get_sessionmaker),
) -> None:
    """Delete a custom role (DELETE).

    Only custom roles can be deleted. Built-in roles reject with 403.

    Args:
        role_id: Role to delete

    Raises:
        403: If role.built_in is True.
        404: If role not found.
        409: If role has bindings (FK constraint).
    """
    async with sm() as session:
        role = await session.get(Role, role_id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role {role_id} not found",
            )

        # Reject deletion of built-in roles
        if role.built_in:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete built-in roles",
            )

        # Check for bindings before deletion
        binding_count = await session.scalar(
            select(func.count()).select_from(Binding).where(Binding.role_id == role_id)
        )
        if binding_count and binding_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete role with {binding_count} active bindings",
            )

        await session.delete(role)
        await session.commit()
        # TODO(T2.4): bump engine perm-cache version on role mutate
        # TODO: emit audit event action="role.deleted" if audit chain available
