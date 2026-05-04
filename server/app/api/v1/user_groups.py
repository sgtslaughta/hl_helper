"""UserGroup CRUD + membership endpoints."""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.models.user import User
from server.app.models.user_group import UserGroup, user_group_members

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["user-groups"])


class UserGroupCreate(BaseModel):
    name: str
    description: str | None = None


class UserGroupOut(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime


class UserGroupMemberAdd(BaseModel):
    user_id: str


@router.post(
    "/user-groups",
    response_model=UserGroupOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_user_group(req: Request, body: UserGroupCreate) -> UserGroupOut:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        group = UserGroup(name=body.name, description=body.description)
        session.add(group)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Group name {body.name} already exists",
            ) from None

    return UserGroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
    )


@router.get(
    "/user-groups",
    response_model=list[UserGroupOut],
    dependencies=[Depends(admin_required)],
)
async def list_user_groups(req: Request) -> list[UserGroupOut]:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        groups = (await session.execute(select(UserGroup))).scalars().all()
    return [
        UserGroupOut(
            id=g.id,
            name=g.name,
            description=g.description,
            created_at=g.created_at,
        )
        for g in groups
    ]


@router.post(
    "/user-groups/{group_id}/members",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def add_user_to_group(
    req: Request, group_id: str, body: UserGroupMemberAdd
) -> dict[str, str]:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        group = await session.scalar(select(UserGroup).where(UserGroup.id == group_id))
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
            )

        user = await session.scalar(select(User).where(User.id == body.user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        try:
            await session.execute(
                insert(user_group_members).values(
                    user_id=body.user_id, user_group_id=group_id
                )
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already in group",
            ) from None

    return {"status": "added"}


@router.delete(
    "/user-groups/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_required)],
)
async def remove_user_from_group(req: Request, group_id: str, user_id: str) -> None:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        membership = await session.scalar(
            select(user_group_members).where(
                (user_group_members.c.user_id == user_id)
                & (user_group_members.c.user_group_id == group_id)
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found"
            )
        await session.execute(
            delete(user_group_members).where(
                (user_group_members.c.user_id == user_id)
                & (user_group_members.c.user_group_id == group_id)
            )
        )
        await session.commit()
