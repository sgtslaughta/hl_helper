"""MaintenanceWindow CRUD API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.models.maintenance_window import MaintenanceWindow

router = APIRouter(
    prefix="/v1/maintenance-windows", tags=["maintenance-windows"]
)


def _validate_cron(value: str) -> str:
    parts = value.strip().split()
    if len(parts) != 5:
        raise PydanticCustomError(
            "cron_format",
            f"cron must have 5 fields, got {len(parts)}",
        )
    return value


class MaintenanceWindowCreate(BaseModel):
    name: str = Field(..., description="Unique window name")
    description: str | None = None
    start_cron: str = Field(..., min_length=1)
    duration_minutes: int = Field(..., gt=0)
    timezone: str = "UTC"
    target_selector: dict[str, object]
    kind: Literal["allow", "blackout"]

    @field_validator("start_cron")
    @classmethod
    def _v(cls, v: str) -> str:
        return _validate_cron(v)


class MaintenanceWindowPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    start_cron: str | None = None
    duration_minutes: int | None = Field(None, gt=0)
    timezone: str | None = None
    target_selector: dict[str, object] | None = None
    kind: Literal["allow", "blackout"] | None = None

    @field_validator("start_cron")
    @classmethod
    def _v(cls, v: str | None) -> str | None:
        return None if v is None else _validate_cron(v)


class MaintenanceWindowOut(BaseModel):
    id: str
    name: str
    description: str | None
    start_cron: str
    duration_minutes: int
    timezone: str
    target_selector: dict[str, object]
    kind: str
    created_at: datetime
    updated_at: datetime


def _to_out(window: MaintenanceWindow) -> MaintenanceWindowOut:
    return MaintenanceWindowOut(
        id=window.id,
        name=window.name,
        description=window.description,
        start_cron=window.start_cron,
        duration_minutes=window.duration_minutes,
        timezone=window.timezone,
        target_selector=window.target_selector,
        kind=window.kind.value,
        created_at=window.created_at,
        updated_at=window.updated_at,
    )


@router.post(
    "",
    response_model=MaintenanceWindowOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_maintenance_window(
    req: Request, body: MaintenanceWindowCreate
) -> MaintenanceWindowOut:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        window = MaintenanceWindow(
            id=str(uuid4()),
            name=body.name,
            description=body.description,
            start_cron=body.start_cron,
            duration_minutes=body.duration_minutes,
            timezone=body.timezone,
            target_selector=body.target_selector,
            kind=body.kind,
        )
        session.add(window)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Maintenance window with this name already exists",
            ) from None
        await session.refresh(window)
    return _to_out(window)


@router.get(
    "",
    response_model=list[MaintenanceWindowOut],
    dependencies=[Depends(admin_required)],
)
async def list_maintenance_windows(req: Request) -> list[MaintenanceWindowOut]:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        rows = (await session.execute(select(MaintenanceWindow))).scalars().all()
    return [_to_out(r) for r in rows]


@router.get(
    "/{window_id}",
    response_model=MaintenanceWindowOut,
    dependencies=[Depends(admin_required)],
)
async def get_maintenance_window(req: Request, window_id: str) -> MaintenanceWindowOut:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        window = (await session.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
        )).scalars().first()
    if window is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )
    return _to_out(window)


@router.patch(
    "/{window_id}",
    response_model=MaintenanceWindowOut,
    dependencies=[Depends(admin_required)],
)
async def update_maintenance_window(
    req: Request, window_id: str, body: MaintenanceWindowPatch
) -> MaintenanceWindowOut:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        window = (await session.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
        )).scalars().first()
        if window is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance window not found",
            )

        data = body.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            window.name = data["name"]
        if "description" in data:
            window.description = data["description"]
        if "start_cron" in data and data["start_cron"] is not None:
            window.start_cron = data["start_cron"]
        if "duration_minutes" in data and data["duration_minutes"] is not None:
            window.duration_minutes = data["duration_minutes"]
        if "timezone" in data and data["timezone"] is not None:
            window.timezone = data["timezone"]
        if "target_selector" in data and data["target_selector"] is not None:
            window.target_selector = data["target_selector"]
        if "kind" in data and data["kind"] is not None:
            window.kind = data["kind"]

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Maintenance window with this name already exists",
            ) from None
        await session.refresh(window)
    return _to_out(window)


@router.delete(
    "/{window_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_required)],
)
async def delete_maintenance_window(req: Request, window_id: str) -> None:
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        window = (await session.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
        )).scalars().first()
        if window is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance window not found",
            )
        await session.delete(window)
        await session.commit()
