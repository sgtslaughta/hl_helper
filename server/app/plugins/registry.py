"""Plugin registry for lifecycle management."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.plugin import Plugin
from server.app.plugins.manifest import PluginManifest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from server.app.audit.sql_chain import SqlAuditChain

log = structlog.get_logger(__name__)

PLUGIN_STATES = ("disabled", "enabled", "paused", "broken")


class PluginError(Exception):
    """Base plugin system error."""

    pass


class PluginNotFoundError(PluginError):
    """Plugin not found."""

    pass


class NotAcknowledgedError(PluginError):
    """Plugin capabilities not acknowledged."""

    pass


class CapabilityMismatchError(PluginError):
    """Acknowledged capabilities do not match manifest."""

    pass


class InvalidStateError(PluginError):
    """Plugin state transition invalid."""

    pass


class PluginRegistry:
    """Manages plugin lifecycle: install, ack, enable, disable."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        audit_chain: SqlAuditChain,
    ) -> None:
        """Initialize registry.

        Args:
            session_maker: Async sessionmaker.
            audit_chain: Audit chain for logging.
        """
        self._sm = session_maker
        self._audit = audit_chain

    async def install(
        self,
        manifest: PluginManifest,
        *,
        actor_id: str,
        session: AsyncSession,
    ) -> Plugin:
        """Install plugin from manifest.

        Creates plugin row with state=disabled. Logs audit entry.

        Args:
            manifest: Plugin manifest.
            actor_id: Installing user ID.
            session: DB session.

        Returns:
            Installed plugin row.
        """
        manifest_dict = manifest.model_dump()
        manifest_json = json.dumps(manifest_dict, sort_keys=True)
        manifest_digest = hashlib.sha256(manifest_json.encode()).hexdigest()

        plugin = Plugin(
            id=manifest.id,
            version=manifest.version,
            state="disabled",
            manifest_json=manifest_json,
            installed_at=datetime.now(timezone.utc),
            installed_by=actor_id,
            disabled_reason=None,
            capability_ack_json=None,
        )
        session.add(plugin)
        await session.flush()

        await self._audit.append(
            session,
            actor=actor_id,
            action="plugin.installed",
            subject=manifest.id,
            payload={
                "version": manifest.version,
                "capabilities": manifest.capabilities,
                "manifest_digest": manifest_digest,
            },
        )

        log.info("plugin_installed", plugin_id=manifest.id, version=manifest.version)
        return plugin

    async def acknowledge_capabilities(
        self,
        plugin_id: str,
        *,
        actor_id: str,
        acked: list[str],
        session: AsyncSession,
    ) -> Plugin:
        """Acknowledge plugin capabilities.

        Validates that acked capabilities are subset of manifest capabilities.
        Stores acknowledgement with timestamp and actor.

        Args:
            plugin_id: Plugin ID.
            actor_id: Acknowledging user ID.
            acked: List of acknowledged capabilities.
            session: DB session.

        Returns:
            Updated plugin row.

        Raises:
            PluginNotFoundError: Plugin not found.
            CapabilityMismatchError: Acked not subset of manifest.
        """
        plugin = await session.get(Plugin, plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"Plugin {plugin_id} not found")

        manifest_dict = json.loads(plugin.manifest_json)
        manifest_capabilities = set(manifest_dict["capabilities"])
        acked_set = set(acked)

        if not acked_set <= manifest_capabilities:
            invalid = acked_set - manifest_capabilities
            raise CapabilityMismatchError(
                f"Acknowledged capabilities not in manifest: {invalid}"
            )

        ack_dict = {
            "acked_capabilities": acked,
            "ack_actor": actor_id,
            "ack_at": datetime.now(timezone.utc).isoformat(),
        }
        plugin.capability_ack_json = json.dumps(ack_dict, sort_keys=True)

        await session.flush()

        await self._audit.append(
            session,
            actor=actor_id,
            action="plugin.capability_ack",
            subject=plugin_id,
            payload={"acked_capabilities": acked},
        )

        log.info(
            "plugin_capability_ack",
            plugin_id=plugin_id,
            acked_count=len(acked),
        )
        return plugin

    async def enable(
        self,
        plugin_id: str,
        *,
        actor_id: str,
        session: AsyncSession,
    ) -> Plugin:
        """Enable plugin.

        Requires capability_ack_json to be set. State must be disabled or paused.

        Args:
            plugin_id: Plugin ID.
            actor_id: Enabling user ID.
            session: DB session.

        Returns:
            Updated plugin row.

        Raises:
            PluginNotFoundError: Plugin not found.
            NotAcknowledgedError: Capabilities not acknowledged.
            InvalidStateError: Invalid state transition.
        """
        plugin = await session.get(Plugin, plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"Plugin {plugin_id} not found")

        if plugin.capability_ack_json is None:
            raise NotAcknowledgedError(
                f"Plugin {plugin_id} capabilities not acknowledged"
            )

        if plugin.state not in ("disabled", "paused"):
            raise InvalidStateError(
                f"Cannot enable plugin in state {plugin.state}"
            )

        plugin.state = "enabled"
        plugin.disabled_reason = None

        await session.flush()

        await self._audit.append(
            session,
            actor=actor_id,
            action="plugin.enabled",
            subject=plugin_id,
        )

        log.info("plugin_enabled", plugin_id=plugin_id)
        return plugin

    async def disable(
        self,
        plugin_id: str,
        *,
        actor_id: str,
        reason: str,
        session: AsyncSession,
    ) -> Plugin:
        """Disable plugin.

        Args:
            plugin_id: Plugin ID.
            actor_id: Disabling user ID.
            reason: Reason for disabling.
            session: DB session.

        Returns:
            Updated plugin row.

        Raises:
            PluginNotFoundError: Plugin not found.
        """
        plugin = await session.get(Plugin, plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"Plugin {plugin_id} not found")

        plugin.state = "disabled"
        plugin.disabled_reason = reason

        await session.flush()

        await self._audit.append(
            session,
            actor=actor_id,
            action="plugin.disabled",
            subject=plugin_id,
            payload={"reason": reason},
        )

        log.info("plugin_disabled", plugin_id=plugin_id, reason=reason)
        return plugin

    async def list_plugins(
        self,
        *,
        state: str | None = None,
        session: AsyncSession,
    ) -> list[Plugin]:
        """List plugins with optional state filter.

        Args:
            state: Filter by state (optional).
            session: DB session.

        Returns:
            List of plugin rows.
        """
        stmt = select(Plugin)
        if state is not None:
            stmt = stmt.where(Plugin.state == state)
        result = await session.execute(stmt)
        return list(result.scalars().all())
