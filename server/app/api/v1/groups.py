"""API routes for groups and group memberships."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from server.app.api.middleware.admin_auth import admin_required
from server.app.models.group import Group
from server.app.models.group_membership import GroupMembership

router = APIRouter(prefix="/v1/groups", tags=["groups"])


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
    kind: str = "static"


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
    sm = req.app.state.sessionmaker
    async with sm() as session:
        # Validate parent_id if provided
        if body.parent_id:
            parent_id_uuid = UUID(body.parent_id)
            result = await session.execute(
                select(Group).where(Group.id == parent_id_uuid)
            )
            if result.scalars().first() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent group not found",
                )

        # Create new group
        parent_uuid: UUID | None = UUID(body.parent_id) if body.parent_id else None
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
    sm = req.app.state.sessionmaker
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
    sm = req.app.state.sessionmaker
    async with sm() as session:
        group_uuid = UUID(group_id)
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
    sm = req.app.state.sessionmaker
    async with sm() as session:
        group_uuid = UUID(group_id)
        result = await session.execute(
            select(Group).where(Group.id == group_uuid)
        )
        group = result.scalars().first()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        # Validate new parent_id if provided
        if body.parent_id:
            parent_uuid = UUID(body.parent_id)
            result = await session.execute(
                select(Group).where(Group.id == parent_uuid)
            )
            if result.scalars().first() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent group not found",
                )
            group.parent_id = parent_uuid

        if body.name is not None:
            group.name = body.name
        if body.description is not None:
            group.description = body.description

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Group with this name already exists",
            )
        await session.refresh(group)

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
    sm = req.app.state.sessionmaker
    async with sm() as session:
        group_uuid = UUID(group_id)
        result = await session.execute(
            select(Group).where(Group.id == group_uuid)
        )
        group = result.scalars().first()

        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        await session.delete(group)
        await session.commit()


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
    sm = req.app.state.sessionmaker
    async with sm() as session:
        group_uuid = UUID(group_id)

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
        await session.commit()


@router.delete(
    "/{group_id}/members/{host_id}",
    status_code=204,
    dependencies=[Depends(admin_required)],
)
async def remove_member(req: Request, group_id: str, host_id: str) -> None:
    """Remove a host from a group.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        group_uuid = UUID(group_id)

        await session.execute(
            delete(GroupMembership).where(
                (GroupMembership.group_id == group_uuid)
                & (GroupMembership.host_id == host_id)
            )
        )
        await session.commit()
