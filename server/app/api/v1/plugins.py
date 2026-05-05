"""Plugins API: stub for plugin lifecycle and registry management."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from server.app.api.middleware.admin_auth import admin_required

router = APIRouter(prefix="/v1/plugins", tags=["plugins"])
log = structlog.get_logger(__name__)


class PluginOut(BaseModel):
    """Plugin response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Plugin ID")
    name: str = Field(..., description="Plugin name")
    version: str = Field(..., description="Plugin version")
    enabled: bool = Field(..., description="Whether plugin is enabled")
    manifest_uri: str = Field(..., description="Plugin manifest URI")


class PluginInstallRequest(BaseModel):
    """Request to install a plugin."""

    manifest_uri: str = Field(..., description="URI to plugin manifest")


class PluginActionResponse(BaseModel):
    """Response for plugin enable/disable actions."""

    ok: bool = Field(..., description="Action success indicator")
    enabled: bool = Field(..., description="New enabled state")


@router.get("", response_model=list[PluginOut])
async def list_plugins(
    actor: str = Depends(admin_required),
) -> list[PluginOut]:
    """List all registered plugins.

    Returns:
        Empty list of registered plugins (TODO: fetch from registry)
    """
    log.info("list_plugins", actor=actor)
    # TODO: Query registered plugins from persistence layer
    return []


@router.post("", response_model=PluginOut, status_code=status.HTTP_201_CREATED)
async def install_plugin(
    body: PluginInstallRequest,
    actor: str = Depends(admin_required),
) -> PluginOut:
    """Install a plugin from manifest URI.

    Args:
        body: Plugin installation request with manifest_uri

    Returns:
        Installed plugin with 201 status
    """
    log.info("install_plugin", manifest_uri=body.manifest_uri, actor=actor)
    # TODO: Fetch manifest, validate, and install plugin
    # TODO: Return generated plugin ID and details
    return PluginOut(
        id="plugin_stub",
        name="stub",
        version="0.0.0",
        enabled=True,
        manifest_uri=body.manifest_uri,
    )


@router.get("/{plugin_id}", response_model=PluginOut)
async def get_plugin(
    plugin_id: str,
    actor: str = Depends(admin_required),
) -> PluginOut:
    """Get a single plugin by ID.

    Args:
        plugin_id: Plugin ID

    Raises:
        404: Plugin not found
    """
    log.info("get_plugin", plugin_id=plugin_id, actor=actor)
    # TODO: Fetch plugin from persistence layer
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Plugin {plugin_id} not found",
    )


@router.post("/{plugin_id}/actions/enable", response_model=PluginActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def enable_plugin(
    plugin_id: str,
    actor: str = Depends(admin_required),
) -> PluginActionResponse:
    """Enable a plugin.

    Args:
        plugin_id: Plugin ID

    Returns:
        Confirmation with enabled=True and 202 status
    """
    log.info("enable_plugin", plugin_id=plugin_id, actor=actor)
    # TODO: Mark plugin as enabled in persistence layer
    return PluginActionResponse(ok=True, enabled=True)


@router.post("/{plugin_id}/actions/disable", response_model=PluginActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def disable_plugin(
    plugin_id: str,
    actor: str = Depends(admin_required),
) -> PluginActionResponse:
    """Disable a plugin.

    Args:
        plugin_id: Plugin ID

    Returns:
        Confirmation with enabled=False and 202 status
    """
    log.info("disable_plugin", plugin_id=plugin_id, actor=actor)
    # TODO: Mark plugin as disabled in persistence layer
    return PluginActionResponse(ok=True, enabled=False)


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
    plugin_id: str,
    actor: str = Depends(admin_required),
) -> None:
    """Delete a plugin.

    Args:
        plugin_id: Plugin ID to delete
    """
    log.info("delete_plugin", plugin_id=plugin_id, actor=actor)
    # TODO: Remove plugin from persistence layer
