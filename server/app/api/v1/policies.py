"""API routes for update policies and maintenance windows."""

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
from server.app.models.update_policy import UpdatePolicy
from server.app.models.maintenance_window import MaintenanceWindow

update_policy_router = APIRouter(prefix="/v1/update-policies", tags=["update-policies"])
maintenance_window_router = APIRouter(prefix="/v1/maintenance-windows", tags=["maintenance-windows"])


# Pydantic models for UpdatePolicy


class UpdatePolicyCreate(BaseModel):
    """Request to create an update policy."""

    name: str = Field(..., description="Unique policy name")
    description: str | None = Field(None, description="Free-text description")
    target_selector: dict[str, object] = Field(..., description="Selector matching hosts/groups this policy applies to")
    auto_apply_classes: list[str] = Field(..., description='Update classes to auto-apply, e.g. ["security"]')
    reboot_policy: Literal["never", "if_required", "always"] = Field(..., description="When to reboot after applying updates")
    breaking_change_policy: Literal["block", "approve", "allow"] = Field(..., description="Behavior when an update is flagged as breaking")
    approval_required: bool = Field(False, description="If true, dispatcher must request approval before applying")


class UpdatePolicyPatch(BaseModel):
    """Request to update an update policy."""

    name: str | None = Field(None, description="Unique policy name")
    description: str | None = Field(None, description="Free-text description")
    target_selector: dict[str, object] | None = Field(None, description="Selector matching hosts/groups this policy applies to")
    auto_apply_classes: list[str] | None = Field(None, description='Update classes to auto-apply, e.g. ["security"]')
    reboot_policy: Literal["never", "if_required", "always"] | None = Field(None, description="When to reboot after applying updates")
    breaking_change_policy: Literal["block", "approve", "allow"] | None = Field(None, description="Behavior when an update is flagged as breaking")
    approval_required: bool | None = Field(None, description="If true, dispatcher must request approval before applying")


class UpdatePolicyOut(BaseModel):
    """Response with update policy details."""

    id: str = Field(..., description="Policy UUID")
    name: str = Field(..., description="Unique policy name")
    description: str | None = Field(None, description="Free-text description")
    target_selector: dict[str, object] = Field(..., description="Selector matching hosts/groups this policy applies to")
    auto_apply_classes: list[str] = Field(..., description='Update classes to auto-apply, e.g. ["security"]')
    reboot_policy: str = Field(..., description="When to reboot after applying updates")
    breaking_change_policy: str = Field(..., description="Behavior when an update is flagged as breaking")
    approval_required: bool = Field(..., description="If true, dispatcher must request approval before applying")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# Pydantic models for MaintenanceWindow


class MaintenanceWindowCreate(BaseModel):
    """Request to create a maintenance window."""

    name: str = Field(..., description="Unique maintenance window name")
    description: str | None = Field(None, description="Free-text description")
    start_cron: str = Field(..., min_length=1, description="Cron expression (5 fields) for start time")
    duration_minutes: int = Field(..., gt=0, description="Window duration in minutes")
    timezone: str = Field("UTC", description="Timezone for cron evaluation")
    target_selector: dict[str, object] = Field(..., description="Selector matching hosts/groups this window applies to")
    kind: Literal["allow", "blackout"] = Field(..., description="Window type: allow or blackout")

    @field_validator("start_cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Validate cron format after model creation."""
        parts = v.strip().split()
        if len(parts) != 5:
            raise PydanticCustomError(
                "cron_format",
                f"cron must have 5 fields, got {len(parts)}",
            )
        return v


class MaintenanceWindowPatch(BaseModel):
    """Request to update a maintenance window."""

    name: str | None = Field(None, description="Unique maintenance window name")
    description: str | None = Field(None, description="Free-text description")
    start_cron: str | None = Field(None, description="Cron expression (5 fields) for start time")
    duration_minutes: int | None = Field(None, gt=0, description="Window duration in minutes")
    timezone: str | None = Field(None, description="Timezone for cron evaluation")
    target_selector: dict[str, object] | None = Field(None, description="Selector matching hosts/groups this window applies to")
    kind: Literal["allow", "blackout"] | None = Field(None, description="Window type: allow or blackout")

    @field_validator("start_cron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        """Validate cron format if provided."""
        if v is not None:
            parts = v.strip().split()
            if len(parts) != 5:
                raise PydanticCustomError(
                    "cron_format",
                    f"cron must have 5 fields, got {len(parts)}",
                )
        return v


class MaintenanceWindowOut(BaseModel):
    """Response with maintenance window details."""

    id: str = Field(..., description="Window UUID")
    name: str = Field(..., description="Unique maintenance window name")
    description: str | None = Field(None, description="Free-text description")
    start_cron: str = Field(..., description="Cron expression (5 fields) for start time")
    duration_minutes: int = Field(..., description="Window duration in minutes")
    timezone: str = Field(..., description="Timezone for cron evaluation")
    target_selector: dict[str, object] = Field(..., description="Selector matching hosts/groups this window applies to")
    kind: str = Field(..., description="Window type: allow or blackout")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# UpdatePolicy endpoints


@update_policy_router.post(
    "",
    response_model=UpdatePolicyOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_update_policy(
    req: Request, body: UpdatePolicyCreate
) -> UpdatePolicyOut:
    """Create a new update policy.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        policy = UpdatePolicy(
            id=str(uuid4()),
            name=body.name,
            description=body.description,
            target_selector=body.target_selector,
            auto_apply_classes=body.auto_apply_classes,
            reboot_policy=body.reboot_policy,
            breaking_change_policy=body.breaking_change_policy,
            approval_required=body.approval_required,
        )
        session.add(policy)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Update policy with this name already exists",
            ) from None
        await session.refresh(policy)

    return UpdatePolicyOut(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        target_selector=policy.target_selector,
        auto_apply_classes=policy.auto_apply_classes,
        reboot_policy=policy.reboot_policy.value,
        breaking_change_policy=policy.breaking_change_policy.value,
        approval_required=policy.approval_required,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@update_policy_router.get(
    "",
    response_model=list[UpdatePolicyOut],
    dependencies=[Depends(admin_required)],
)
async def list_update_policies(req: Request) -> list[UpdatePolicyOut]:
    """List all update policies.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(select(UpdatePolicy))
        rows = result.scalars().all()

    return [
        UpdatePolicyOut(
            id=r.id,
            name=r.name,
            description=r.description,
            target_selector=r.target_selector,
            auto_apply_classes=r.auto_apply_classes,
            reboot_policy=r.reboot_policy.value,
            breaking_change_policy=r.breaking_change_policy.value,
            approval_required=r.approval_required,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@update_policy_router.get(
    "/{policy_id}",
    response_model=UpdatePolicyOut,
    dependencies=[Depends(admin_required)],
)
async def get_update_policy(req: Request, policy_id: str) -> UpdatePolicyOut:
    """Get a single update policy by id.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(UpdatePolicy).where(UpdatePolicy.id == policy_id)
        )
        policy = result.scalars().first()

    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Update policy not found",
        )

    return UpdatePolicyOut(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        target_selector=policy.target_selector,
        auto_apply_classes=policy.auto_apply_classes,
        reboot_policy=policy.reboot_policy.value,
        breaking_change_policy=policy.breaking_change_policy.value,
        approval_required=policy.approval_required,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@update_policy_router.patch(
    "/{policy_id}",
    response_model=UpdatePolicyOut,
    dependencies=[Depends(admin_required)],
)
async def update_update_policy(
    req: Request, policy_id: str, body: UpdatePolicyPatch
) -> UpdatePolicyOut:
    """Update an update policy.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(UpdatePolicy).where(UpdatePolicy.id == policy_id)
        )
        policy = result.scalars().first()

        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Update policy not found",
            )

        # Handle field updates using model_dump(exclude_unset=True)
        data = body.model_dump(exclude_unset=True)

        if "name" in data and data["name"] is not None:
            policy.name = data["name"]
        if "description" in data:
            policy.description = data["description"]
        if "target_selector" in data and data["target_selector"] is not None:
            policy.target_selector = data["target_selector"]
        if "auto_apply_classes" in data and data["auto_apply_classes"] is not None:
            policy.auto_apply_classes = data["auto_apply_classes"]
        if "reboot_policy" in data and data["reboot_policy"] is not None:
            policy.reboot_policy = data["reboot_policy"]
        if "breaking_change_policy" in data and data["breaking_change_policy"] is not None:
            policy.breaking_change_policy = data["breaking_change_policy"]
        if "approval_required" in data and data["approval_required"] is not None:
            policy.approval_required = data["approval_required"]

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Update policy with this name already exists",
            ) from None
        await session.refresh(policy)

    return UpdatePolicyOut(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        target_selector=policy.target_selector,
        auto_apply_classes=policy.auto_apply_classes,
        reboot_policy=policy.reboot_policy.value,
        breaking_change_policy=policy.breaking_change_policy.value,
        approval_required=policy.approval_required,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@update_policy_router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_required)],
)
async def delete_update_policy(req: Request, policy_id: str) -> None:
    """Delete an update policy.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(UpdatePolicy).where(UpdatePolicy.id == policy_id)
        )
        policy = result.scalars().first()

        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Update policy not found",
            )

        await session.delete(policy)
        await session.commit()


# MaintenanceWindow endpoints


@maintenance_window_router.post(
    "",
    response_model=MaintenanceWindowOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_required)],
)
async def create_maintenance_window(
    req: Request, body: MaintenanceWindowCreate
) -> MaintenanceWindowOut:
    """Create a new maintenance window.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
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


@maintenance_window_router.get(
    "",
    response_model=list[MaintenanceWindowOut],
    dependencies=[Depends(admin_required)],
)
async def list_maintenance_windows(req: Request) -> list[MaintenanceWindowOut]:
    """List all maintenance windows.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(select(MaintenanceWindow))
        rows = result.scalars().all()

    return [
        MaintenanceWindowOut(
            id=r.id,
            name=r.name,
            description=r.description,
            start_cron=r.start_cron,
            duration_minutes=r.duration_minutes,
            timezone=r.timezone,
            target_selector=r.target_selector,
            kind=r.kind.value,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@maintenance_window_router.get(
    "/{window_id}",
    response_model=MaintenanceWindowOut,
    dependencies=[Depends(admin_required)],
)
async def get_maintenance_window(req: Request, window_id: str) -> MaintenanceWindowOut:
    """Get a single maintenance window by id.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
        )
        window = result.scalars().first()

    if window is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )

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


@maintenance_window_router.patch(
    "/{window_id}",
    response_model=MaintenanceWindowOut,
    dependencies=[Depends(admin_required)],
)
async def update_maintenance_window(
    req: Request, window_id: str, body: MaintenanceWindowPatch
) -> MaintenanceWindowOut:
    """Update a maintenance window.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
        )
        window = result.scalars().first()

        if window is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance window not found",
            )

        # Handle field updates using model_dump(exclude_unset=True)
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


@maintenance_window_router.delete(
    "/{window_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_required)],
)
async def delete_maintenance_window(req: Request, window_id: str) -> None:
    """Delete a maintenance window.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
        )
        window = result.scalars().first()

        if window is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance window not found",
            )

        await session.delete(window)
        await session.commit()
