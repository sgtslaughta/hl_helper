"""User, UserGroup, and ServiceAccount CRUD endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Discriminator, EmailStr, Tag, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models.user import User, UserKind

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

