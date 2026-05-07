"""Settings API: GET effective config + source per key, PATCH runtime-mutable keys.

Scope-based mutability ensures boot-only settings require restart, env-locked settings
reflect their env var source, and runtime-mutable settings can be changed at runtime.
Secret redaction protects sensitive values in API responses and audit logs for keys
in SECRET_FIELDS (vault_token, admin_token, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from server.app.api.state import get_app_state
from server.app.api.middleware.admin_auth import admin_required
from server.app.models import Setting
from server.app.models.setting import SettingSource
from server.app.settings.config import load_settings, SECRET_FIELDS, scope_for

router = APIRouter(prefix="/v1/settings", tags=["settings"])
log = structlog.get_logger(__name__)


class EffectiveSetting(BaseModel):
    """Effective setting value with source and scope metadata.

    Redacted is True for SECRET_FIELDS to indicate the value has been masked.
    """
    key: str = Field(..., description="Setting key, e.g. 'ui.theme'")
    value: Any = Field(..., description="Effective value; redacted if secret")
    source: str = Field(..., description="Origin: 'runtime' | 'env' | 'file' | 'default'")
    scope: str = Field(..., description="Mutability: 'boot-only' | 'runtime-mutable' | 'env-locked'")
    redacted: bool = Field(False, description="True if key is in SECRET_FIELDS")


class PatchRequest(BaseModel):
    """Request to update a runtime-mutable setting."""
    key: str = Field(..., description="Setting key to update")
    value: Any = Field(..., description="New value for the setting")


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
    sm = get_app_state(req).sessionmaker
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
    # Add any model field not yet in the DB (default source). Use scope_for
    # so runtime-mutable keys (public_url, log_level, etc.) advertise the
    # right scope and the UI can render edit controls.
    for field_name in live.model_dump().keys():
        if field_name in seen:
            continue
        value, redacted = _redacted(field_name, getattr(live, field_name, None))
        out.append(EffectiveSetting(
            key=field_name, value=value, source="default",
            scope=scope_for(field_name).value, redacted=redacted,
        ))
    return out


@router.patch("", status_code=200, dependencies=[Depends(admin_required)])
async def patch_setting(req: Request, body: PatchRequest) -> EffectiveSetting:
    """Update a runtime-mutable setting; reject boot-only / env-locked.

    TODO(C2): wire reload signal to in-process event bus once Phase 7 lands.
    """
    state = get_app_state(req)
    sm = state.sessionmaker
    audit = state.audit_chain

    async with sm() as session:
        existing = await session.scalar(
            select(Setting).where(Setting.key == body.key).with_for_update()
        )

        # If no DB row exists, this is a first-time write of a known model
        # field. Validate against the live Pydantic settings model and
        # upsert with scope from scope_for() so runtime-mutable keys (e.g.
        # public_url) can be edited from the UI without a prior seed.
        if existing is None:
            live = load_settings()
            if body.key not in live.model_dump():
                raise HTTPException(404, detail=f"unknown_setting: {body.key}")
            inferred_scope = scope_for(body.key).value
            if inferred_scope == "boot-only":
                raise HTTPException(
                    403,
                    detail=f"boot_only_immutable: {body.key} (restart required)",
                )
            existing = Setting(
                key=body.key,
                value=body.value,
                source=SettingSource.RUNTIME,
                scope=inferred_scope,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(existing)
            old_value = None
        else:
            if existing.scope == "boot-only":
                raise HTTPException(403,
                    detail=f"boot_only_immutable: {body.key} (restart required)")
            if existing.scope == "env-locked":
                raise HTTPException(403,
                    detail=f"env_locked: {body.key} (managed by FLEET_* env var; "
                           "unset env or change scope to runtime-mutable)")
            old_value = existing.value

        new_value = body.value
        audit_old: object
        audit_new: object
        if body.key in SECRET_FIELDS:
            audit_old = "***REDACTED***"
            audit_new = "***REDACTED***"
        else:
            audit_old = old_value
            audit_new = new_value

        # Apply
        existing.value = body.value
        existing.source = SettingSource.RUNTIME
        existing.updated_at = datetime.now(timezone.utc)
        await session.commit()

        # Emit audit in separate transaction
        if audit is not None:
            async with sm() as audit_session:
                await audit.append(
                    audit_session,
                    actor="admin",
                    action="setting.write",
                    subject=body.key,
                    payload={"old": audit_old, "new": audit_new, "source": "runtime"},
                )
                await audit_session.commit()

        # Apply live effect for keys whose runtime behavior depends on
        # AppState rather than a re-read of FleetSettings. Without this, a
        # PATCH lands in the DB but the server keeps minting install commands
        # against the old origin until restart.
        if body.key == "public_url" and isinstance(body.value, str):
            from server.app.lifespan import _enumerate_advertised_origins

            state.public_url = body.value
            state.public_origin = body.value
            state.advertised_origins = _enumerate_advertised_origins(body.value)

        # Emit reload signal placeholder
        log.info("settings.runtime_changed", key=body.key, scope=existing.scope)

        value, redacted = _redacted(existing.key, existing.value)
        return EffectiveSetting(
            key=existing.key, value=value, source=existing.source,
            scope=existing.scope, redacted=redacted,
        )
