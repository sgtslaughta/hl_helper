"""Settings API: GET effective config + source per key, PATCH runtime-mutable keys."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from server.app.api.middleware.admin_auth import admin_required
from server.app.models import Setting
from server.app.settings.config import load_settings, SECRET_FIELDS

router = APIRouter(prefix="/v1/settings", tags=["settings"])


class EffectiveSetting(BaseModel):
    key: str
    value: Any
    source: str  # "runtime" | "env" | "file" | "default"
    scope: str   # "boot-only" | "runtime-mutable" | "env-locked"
    redacted: bool = False  # true if key is in SECRET_FIELDS


class PatchRequest(BaseModel):
    key: str
    value: Any


def _redacted(key: str, value: Any) -> tuple[Any, bool]:
    """Replace secret values with sentinel."""
    if key in SECRET_FIELDS:
        return ("***REDACTED***", True)
    return (value, False)


@router.get("", response_model=list[EffectiveSetting],
            dependencies=[Depends(admin_required)])
async def list_settings(req: Request) -> list[EffectiveSetting]:
    """Return effective settings: DB rows merged with the live Settings model.

    DB rows take precedence (they capture runtime-mutable overrides written
    via PATCH). Keys present only in the Pydantic model are reported with
    source="default" and scope="boot-only" (until classified by the runtime).
    """
    sm = req.app.state.sessionmaker
    db_rows: dict[str, Setting] = {}
    async with sm() as session:
        for s in (await session.execute(select(Setting))).scalars().all():
            db_rows[s.key] = s

    # Pull live in-memory model
    live = load_settings()
    out: list[EffectiveSetting] = []
    seen: set[str] = set()
    for s in db_rows.values():
        value, redacted = _redacted(s.key, s.value)
        out.append(EffectiveSetting(
            key=s.key, value=value, source=s.source, scope=s.scope, redacted=redacted,
        ))
        seen.add(s.key)
    # Add any model field not yet in the DB (default source)
    for field_name in live.model_dump().keys():
        if field_name in seen:
            continue
        value, redacted = _redacted(field_name, getattr(live, field_name, None))
        out.append(EffectiveSetting(
            key=field_name, value=value, source="default",
            scope="boot-only", redacted=redacted,
        ))
    return out


@router.patch("", status_code=200, dependencies=[Depends(admin_required)])
async def patch_setting(req: Request, body: PatchRequest) -> EffectiveSetting:
    """Update a runtime-mutable setting; reject boot-only / env-locked."""
    sm = req.app.state.sessionmaker
    audit = getattr(req.app.state, "audit_chain", None)

    async with sm() as session:
        existing = await session.scalar(
            select(Setting).where(Setting.key == body.key)
        )
        if existing is None:
            raise HTTPException(404, detail=f"unknown_setting: {body.key}")
        if existing.scope == "boot-only":
            raise HTTPException(403,
                detail=f"boot_only_immutable: {body.key} (restart required)")
        if existing.scope == "env-locked":
            raise HTTPException(403,
                detail=f"env_locked: {body.key} (managed by FLEET_* env var; "
                       "unset env or change scope to runtime-mutable)")

        # Apply
        existing.value = body.value
        existing.source = "runtime"
        existing.updated_at = datetime.now(timezone.utc)
        await session.commit()
        if audit is not None:
            await audit.append(
                session,
                actor="admin",
                action="setting.write",
                subject=body.key,
                payload={"new_source": "runtime"},
            )
        value, redacted = _redacted(existing.key, existing.value)
        return EffectiveSetting(
            key=existing.key, value=value, source=existing.source,
            scope=existing.scope, redacted=redacted,
        )
