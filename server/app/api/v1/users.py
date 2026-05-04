"""User, UserGroup, and ServiceAccount CRUD endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Discriminator, EmailStr, Tag, field_validator
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models.user import User, UserKind
from server.app.models.user_group import UserGroup, user_group_members
from server.app.models.service_account import ServiceAccount

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["users"])
log = structlog.get_logger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class UserCreateLocal(BaseModel):
    """Create a local user."""

    model_config = {"extra": "forbid"}

    email: EmailStr
    kind: Literal["local"] = "local"
    display_name: str | None = None
    password_hash: str | None = None


class UserCreateOidc(BaseModel):
    """Create an OIDC user."""

    model_config = {"extra": "forbid"}

    email: EmailStr
    kind: Literal["oidc"]
    oidc_subject: str
    oidc_issuer: str
    display_name: str | None = None

    @field_validator("oidc_subject", "oidc_issuer")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("cannot be empty")
        return v


# Discriminated union: kind field determines which model to use
UserCreate = Annotated[
    Union[
        Annotated[UserCreateLocal, Tag("local")],
        Annotated[UserCreateOidc, Tag("oidc")],
    ],
    Discriminator("kind"),
]


class UserUpdate(BaseModel):
    """Update a user."""

    display_name: str | None = None
    disabled: bool | None = None


class UserOut(BaseModel):
    """User response."""

    id: str
    email: str
    display_name: str | None
    kind: str
    oidc_subject: str | None
    oidc_issuer: str | None
    disabled: bool
    created_at: datetime
    updated_at: datetime


class UserGroupCreate(BaseModel):
    """Create a user group."""

    name: str
    description: str | None = None


class UserGroupOut(BaseModel):
    """User group response."""

    id: str
    name: str
    description: str | None
    created_at: datetime


class UserGroupMemberAdd(BaseModel):
    """Add a member to a user group."""

    user_id: str


class ServiceAccountCreate(BaseModel):
    """Create a service account."""

    name: str
    description: str | None = None


class ServiceAccountOut(BaseModel):
    """Service account response."""

    id: str
    name: str
    description: str | None
    disabled: bool
    created_at: datetime


class ServiceAccountUpdate(BaseModel):
    """Update a service account."""

    disabled: bool | None = None
    description: str | None = None


# ============================================================================
# User Endpoints
# ============================================================================


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_user(req: Request, body: UserCreate) -> UserOut:
    """Create a new user (local or OIDC).

    Local users can have an optional password_hash (pre-computed by caller).
    OIDC users require oidc_subject and oidc_issuer; password_hash is rejected.
    """
    sm = get_app_state(req).sessionmaker

    async with sm() as session:
        user = User(
            email=body.email,
            kind=UserKind(body.kind),
            display_name=body.display_name,
            oidc_subject=getattr(body, "oidc_subject", None),
            oidc_issuer=getattr(body, "oidc_issuer", None),
            password_hash=getattr(body, "password_hash", None),
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email {body.email} already exists",
            ) from None

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="user.created",
                    subject=user.id,
                    payload={"email": user.email, "kind": user.kind.value},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)

    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        kind=user.kind.value,
        oidc_subject=user.oidc_subject,
        oidc_issuer=user.oidc_issuer,
        disabled=user.disabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get(
    "/users",
    response_model=list[UserOut],
    dependencies=[Depends(admin_required)],
)
async def list_users(req: Request) -> list[UserOut]:
    """List all users (including disabled)."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        users = (await session.execute(select(User))).scalars().all()
    return [
        UserOut(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            kind=u.kind.value,
            oidc_subject=u.oidc_subject,
            oidc_issuer=u.oidc_issuer,
            disabled=u.disabled,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(admin_required)],
)
async def get_user(req: Request, user_id: str) -> UserOut:
    """Get a user by ID."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        kind=user.kind.value,
        oidc_subject=user.oidc_subject,
        oidc_issuer=user.oidc_issuer,
        disabled=user.disabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(admin_required)],
)
async def update_user(req: Request, user_id: str, body: UserUpdate) -> UserOut:
    """Update user display_name and/or disabled flag."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        user = await session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if body.display_name is not None:
            user.display_name = body.display_name
        if body.disabled is not None:
            user.disabled = body.disabled
        await session.commit()

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="user.updated",
                    subject=user.id,
                    payload={"email": user.email, "fields_changed": list(body.model_dump(exclude_unset=True).keys())},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)

    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        kind=user.kind.value,
        oidc_subject=user.oidc_subject,
        oidc_issuer=user.oidc_issuer,
        disabled=user.disabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_required)],
)
async def delete_user(req: Request, user_id: str) -> None:
    """Hard delete a user."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user_email = user.email
        try:
            await session.delete(user)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete user with existing bindings",
            ) from None

        # Emit audit event
        app_state = get_app_state(req)
        async with app_state.sessionmaker() as audit_session:
            try:
                await app_state.audit_chain.append(
                    audit_session,
                    actor="admin",
                    action="user.deleted",
                    subject=user_id,
                    payload={"email": user_email},
                )
                await audit_session.commit()
            except Exception as e:
                log.exception("audit_append_failed", exc=e)


# ============================================================================
# UserGroup Endpoints
# ============================================================================


@router.post(
    "/user-groups",
    response_model=UserGroupOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_user_group(req: Request, body: UserGroupCreate) -> UserGroupOut:
    """Create a new user group."""
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
    """List all user groups."""
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
    """Add a user to a user group."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        # Verify group exists
        group = await session.scalar(select(UserGroup).where(UserGroup.id == group_id))
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
            )

        # Verify user exists
        user = await session.scalar(select(User).where(User.id == body.user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # Add membership
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
    """Remove a user from a user group."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        # Check if membership exists
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


# ============================================================================
# ServiceAccount Endpoints
# ============================================================================


@router.post(
    "/service-accounts",
    response_model=ServiceAccountOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_service_account(req: Request, body: ServiceAccountCreate) -> ServiceAccountOut:
    """Create a new service account."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        sa = ServiceAccount(name=body.name, description=body.description)
        session.add(sa)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Service account name {body.name} already exists",
            ) from None

    return ServiceAccountOut(
        id=sa.id,
        name=sa.name,
        description=sa.description,
        disabled=sa.disabled,
        created_at=sa.created_at,
    )


@router.get(
    "/service-accounts",
    response_model=list[ServiceAccountOut],
    dependencies=[Depends(admin_required)],
)
async def list_service_accounts(req: Request) -> list[ServiceAccountOut]:
    """List all service accounts."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        accounts = (await session.execute(select(ServiceAccount))).scalars().all()
    return [
        ServiceAccountOut(
            id=a.id,
            name=a.name,
            description=a.description,
            disabled=a.disabled,
            created_at=a.created_at,
        )
        for a in accounts
    ]


@router.patch(
    "/service-accounts/{sa_id}",
    response_model=ServiceAccountOut,
    dependencies=[Depends(admin_required)],
)
async def patch_service_account(
    req: Request, sa_id: str, body: ServiceAccountUpdate
) -> ServiceAccountOut:
    """Update service account disabled flag and/or description."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        sa = await session.scalar(
            select(ServiceAccount).where(ServiceAccount.id == sa_id).with_for_update()
        )
        if sa is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found"
            )
        data = body.model_dump(exclude_unset=True)
        if "disabled" in data:
            sa.disabled = data["disabled"]
        if "description" in data:
            sa.description = data["description"]
        await session.commit()

    return ServiceAccountOut(
        id=sa.id,
        name=sa.name,
        description=sa.description,
        disabled=sa.disabled,
        created_at=sa.created_at,
    )


@router.delete(
    "/service-accounts/{sa_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_required)],
)
async def delete_service_account(req: Request, sa_id: str) -> None:
    """Delete a service account."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        sa = await session.scalar(select(ServiceAccount).where(ServiceAccount.id == sa_id))
        if sa is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Service account not found"
            )
        try:
            await session.delete(sa)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete service account with existing bindings",
            ) from None
