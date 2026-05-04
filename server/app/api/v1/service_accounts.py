"""ServiceAccount CRUD endpoints."""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.models.service_account import ServiceAccount

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["service-accounts"])


class ServiceAccountCreate(BaseModel):
    name: str
    description: str | None = None


class ServiceAccountOut(BaseModel):
    id: str
    name: str
    description: str | None
    disabled: bool
    created_at: datetime


class ServiceAccountUpdate(BaseModel):
    disabled: bool | None = None
    description: str | None = None


@router.post(
    "/service-accounts",
    response_model=ServiceAccountOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_service_account(
    req: Request, body: ServiceAccountCreate
) -> ServiceAccountOut:
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
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        sa = await session.scalar(
            select(ServiceAccount).where(ServiceAccount.id == sa_id).with_for_update()
        )
        if sa is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service account not found",
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
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        sa = await session.scalar(
            select(ServiceAccount).where(ServiceAccount.id == sa_id)
        )
        if sa is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service account not found",
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
