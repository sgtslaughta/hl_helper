"""API routes for groups and group memberships."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models.group import Group
from server.app.models.group_membership import GroupMembership

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/groups", tags=["groups"])


# Helpers
async def _would_create_cycle(
    session: object, group_id: str, new_parent_id: str | None
) -> bool:
    """Check if assigning new_parent_id to group_id would create a cycle."""
    if new_parent_id is None:
        return False
    if new_parent_id == group_id:
        return True
    cur: str | None = new_parent_id
    seen: set[str] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        if cur == group_id:
            return True
        try:
            parent_uuid = UUID(cur)
        except (ValueError, AttributeError):
            # Invalid UUID format in chain; skip cycle check
            return False
        result = await session.execute(  # type: ignore[attr-defined]
            select(Group.parent_id).where(Group.id == parent_uuid)
        )
        parent: UUID | None = result.scalar()
        cur = str(parent) if parent else None
    return False


# Pydantic models
class GroupCreate(BaseModel):
    """Request to create a new group."""

    name: str
    parent_id: str | None = None
    description: str | None = None


class GroupUpdate(BaseModel):
    """Request to update a group."""

    name: str | None = None
    parent_id: str | None = None
    description: str | None = None


class GroupOut(BaseModel):
    """Response with group details."""

    id: str
    name: str
    parent_id: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class MemberAdd(BaseModel):
    """Request to add a member to a group."""

    host_id: str
    kind: Literal["static", "dynamic"] = "static"


@router.post(
    "",
    response_model=GroupOut,
    status_code=201,
    dependencies=[Depends(admin_required)],
)
async def create_group(req: Request, body: GroupCreate) -> GroupOut:
    """Create a new group.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        # Validate parent_id if provided
        parent_uuid: UUID | None = None
        if body.parent_id:
            try:
                parent_uuid = UUID(body.parent_id)
            except (ValueError, AttributeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"invalid_uuid: {body.parent_id}",
                )
            result = await session.execute(
                select(Group).where(Group.id == parent_uuid)
            )
            if result.scalars().first() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent group not found",
                )

        # Create new group
        group = Group(
            name=body.name,
            parent_id=parent_uuid,
            description=body.description,
        )
        session.add(group)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Group with this name already exists",
            )
        await session.refresh(group)

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="group.created",
                    subject=str(group.id),
                    payload={"name": group.name},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)

    return GroupOut(
        id=str(group.id),
        name=group.name,
        parent_id=str(group.parent_id) if group.parent_id else None,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get(
    "",
    response_model=list[GroupOut],
    dependencies=[Depends(admin_required)],
)
async def list_groups(req: Request) -> list[GroupOut]:
    """List all groups.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        result = await session.execute(select(Group))
        rows = result.scalars().all()

    return [
        GroupOut(
            id=str(r.id),
            name=r.name,
            parent_id=str(r.parent_id) if r.parent_id else None,
            description=r.description,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get(
    "/{group_id}",
    response_model=GroupOut,
    dependencies=[Depends(admin_required)],
)
async def get_group(req: Request, group_id: str) -> GroupOut:
    """Get a single group by id.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        try:
            group_uuid = UUID(group_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid_uuid: {group_id}",
            )
        result = await session.execute(
            select(Group).where(Group.id == group_uuid)
        )
        group = result.scalars().first()

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    return GroupOut(
        id=str(group.id),
        name=group.name,
        parent_id=str(group.parent_id) if group.parent_id else None,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.patch(
    "/{group_id}",
    response_model=GroupOut,
    dependencies=[Depends(admin_required)],
)
async def update_group(
    req: Request, group_id: str, body: GroupUpdate
) -> GroupOut:
    """Update a group's name, description, or parent_id.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        try:
            group_uuid = UUID(group_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid_uuid: {group_id}",
            )
        result = await session.execute(
            select(Group).where(Group.id == group_uuid)
        )
        group = result.scalars().first()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        # Handle field updates using model_dump(exclude_unset=True)
        data = body.model_dump(exclude_unset=True)

        # Validate and apply parent_id if in request
        if "parent_id" in data:
            new_parent_id = data["parent_id"]
            if new_parent_id is not None:
                # Check for circular reference
                if await _would_create_cycle(session, group_id, new_parent_id):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="circular_reference_detected",
                    )
                # Validate parent exists
                try:
                    parent_uuid = UUID(new_parent_id)
                except (ValueError, AttributeError):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"invalid_uuid: {new_parent_id}",
                    )
                result = await session.execute(
                    select(Group).where(Group.id == parent_uuid)
                )
                if result.scalars().first() is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Parent group not found",
                    )
                group.parent_id = parent_uuid
            else:
                # Explicit None = clear parent
                group.parent_id = None

        # Apply name if in request and not None
        if "name" in data and data["name"] is not None:
            group.name = data["name"]

        # Apply description if in request (can be None to clear)
        if "description" in data:
            group.description = data["description"]

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Group with this name already exists",
            )
        await session.refresh(group)

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="group.updated",
                    subject=str(group.id),
                    payload={"name": group.name, "fields_changed": list(data.keys())},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)

    return GroupOut(
        id=str(group.id),
        name=group.name,
        parent_id=str(group.parent_id) if group.parent_id else None,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.delete(
    "/{group_id}",
    status_code=204,
    dependencies=[Depends(admin_required)],
)
async def delete_group(req: Request, group_id: str) -> None:
    """Delete a group.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        try:
            group_uuid = UUID(group_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid_uuid: {group_id}",
            )
        result = await session.execute(
            select(Group).where(Group.id == group_uuid)
        )
        group = result.scalars().first()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        group_name = group.name
        try:
            await session.delete(group)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="group_has_dependents",
            )

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="group.deleted",
                    subject=group_id,
                    payload={"name": group_name},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)


@router.post(
    "/{group_id}/members",
    status_code=201,
    dependencies=[Depends(admin_required)],
)
async def add_member(
    req: Request, group_id: str, body: MemberAdd
) -> None:
    """Add a host to a group.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        try:
            group_uuid = UUID(group_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid_uuid: {group_id}",
            )

        # Verify group exists
        result = await session.execute(
            select(Group).where(Group.id == group_uuid)
        )
        if result.scalars().first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        # Add membership
        membership = GroupMembership(
            host_id=body.host_id,
            group_id=group_uuid,
            kind=body.kind,
        )
        session.add(membership)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "FOREIGN KEY" in msg or "foreign key" in msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="host_not_found",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="already_member",
            )


@router.delete(
    "/{group_id}/members/{host_id}",
    status_code=204,
    dependencies=[Depends(admin_required)],
)
async def remove_member(req: Request, group_id: str, host_id: str) -> None:
    """Remove a host from a group.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        try:
            group_uuid = UUID(group_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid_uuid: {group_id}",
            )

        # Query first to check existence
        existing = await session.scalar(
            select(GroupMembership).where(
                (GroupMembership.group_id == group_uuid)
                & (GroupMembership.host_id == host_id)
            )
        )
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="membership_not_found",
            )

        await session.delete(existing)
        await session.commit()
