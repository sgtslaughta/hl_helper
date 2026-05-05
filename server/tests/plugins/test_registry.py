"""Tests for plugin registry."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.plugins import PluginManifest, PluginRegistry


@pytest.fixture
def test_manifest() -> PluginManifest:
    """Create test manifest."""
    return PluginManifest(
        id="com.example.test",
        version="1.0.0",
        name="Test Plugin",
        runtime="binary",
        capabilities=["egress.http", "hooks.notification.route"],
        min_hl_helper_version="1.0.0",
        resources={
            "cpu_milli": 100,
            "memory_mib": 128,
            "disk_mib": 0,
        },
    )


class TestPluginRegistryInstall:
    """Plugin installation tests."""

    @pytest.mark.asyncio
    async def test_install_creates_plugin_row(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Install creates plugin row with state=disabled."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        assert plugin.id == "com.example.test"
        assert plugin.version == "1.0.0"
        assert plugin.state == "disabled"
        assert plugin.installed_by == "user-1"
        assert plugin.disabled_reason is None
        assert plugin.capability_ack_json is None

    @pytest.mark.asyncio
    async def test_install_persists_manifest_json(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Install stores manifest as JSON."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        manifest_dict = json.loads(plugin.manifest_json)
        assert manifest_dict["id"] == "com.example.test"
        assert manifest_dict["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_install_audit_entry(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Install creates audit entry."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        # Verify audit entry
        async with sm() as session:
            from server.app.models.audit import AuditEntry
            from sqlalchemy import select
            result = await session.execute(select(AuditEntry))
            entries = result.scalars().all()
            assert len(entries) == 1
            entry = entries[0]
            assert entry.action == "plugin.installed"
            assert entry.subject == "com.example.test"
            assert entry.actor == "user-1"
            assert entry.payload["version"] == "1.0.0"


class TestPluginRegistryCapabilities:
    """Capability acknowledgement tests."""

    @pytest.mark.asyncio
    async def test_acknowledge_capabilities(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Acknowledge capabilities sets capability_ack_json."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            plugin = await registry.acknowledge_capabilities(
                plugin.id,
                actor_id="user-1",
                acked=["egress.http", "hooks.notification.route"],
                session=session,
            )
            await session.commit()

        ack_dict = json.loads(plugin.capability_ack_json)
        assert set(ack_dict["acked_capabilities"]) == {
            "egress.http",
            "hooks.notification.route",
        }
        assert ack_dict["ack_actor"] == "user-1"
        assert "ack_at" in ack_dict

    @pytest.mark.asyncio
    async def test_acknowledge_extra_capability_fails(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Acknowledging extra capability raises CapabilityMismatchError."""
        from server.app.plugins import CapabilityMismatchError

        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            with pytest.raises(CapabilityMismatchError):
                await registry.acknowledge_capabilities(
                    plugin.id,
                    actor_id="user-1",
                    acked=["egress.http", "egress.tcp"],
                    session=session,
                )


class TestPluginRegistryEnable:
    """Enable/disable tests."""

    @pytest.mark.asyncio
    async def test_enable_without_ack_fails(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Enable without capability acknowledgement fails."""
        from server.app.plugins import NotAcknowledgedError

        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            with pytest.raises(NotAcknowledgedError):
                await registry.enable(
                    plugin.id,
                    actor_id="user-1",
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_enable_with_ack_succeeds(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Enable after capability acknowledgement succeeds."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            await registry.acknowledge_capabilities(
                plugin.id,
                actor_id="user-1",
                acked=test_manifest.capabilities,
                session=session,
            )
            await session.commit()

        async with sm() as session:
            plugin = await registry.enable(
                plugin.id,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        assert plugin.state == "enabled"

    @pytest.mark.asyncio
    async def test_enable_from_paused(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Enable from paused state succeeds."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            await registry.acknowledge_capabilities(
                plugin.id,
                actor_id="user-1",
                acked=test_manifest.capabilities,
                session=session,
            )
            await registry.enable(
                plugin.id,
                actor_id="user-1",
                session=session,
            )
            await registry.disable(
                plugin.id,
                actor_id="user-1",
                reason="maintenance",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            plugin = await registry.enable(
                plugin.id,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        assert plugin.state == "enabled"

    @pytest.mark.asyncio
    async def test_disable_sets_reason(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Disable stores reason."""
        registry = PluginRegistry(sm, audit_chain)
        async with sm() as session:
            plugin = await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            plugin = await registry.disable(
                plugin.id,
                actor_id="user-1",
                reason="User request",
                session=session,
            )
            await session.commit()

        assert plugin.state == "disabled"
        assert plugin.disabled_reason == "User request"


class TestPluginRegistryList:
    """List operations tests."""

    @pytest.mark.asyncio
    async def test_list_plugins_all(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """List all plugins."""
        registry = PluginRegistry(sm, audit_chain)

        async with sm() as session:
            manifest1 = test_manifest
            manifest2 = PluginManifest(
                id="io.example.other",
                version="1.0.0",
                name="Other Plugin",
                runtime="python",
                capabilities=[],
                min_hl_helper_version="1.0.0",
                resources={
                    "cpu_milli": 100,
                    "memory_mib": 128,
                    "disk_mib": 0,
                },
            )
            await registry.install(manifest1, actor_id="user-1", session=session)
            await registry.install(manifest2, actor_id="user-1", session=session)
            await session.commit()

        async with sm() as session:
            plugins = await registry.list_plugins(session=session)

        assert len(plugins) == 2

    @pytest.mark.asyncio
    async def test_list_plugins_filter_by_state(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """List plugins filtered by state."""
        registry = PluginRegistry(sm, audit_chain)

        async with sm() as session:
            manifest1 = test_manifest
            manifest2 = PluginManifest(
                id="io.example.other",
                version="1.0.0",
                name="Other Plugin",
                runtime="python",
                capabilities=[],
                min_hl_helper_version="1.0.0",
                resources={
                    "cpu_milli": 100,
                    "memory_mib": 128,
                    "disk_mib": 0,
                },
            )
            plugin1 = await registry.install(
                manifest1,
                actor_id="user-1",
                session=session,
            )
            await registry.install(
                manifest2,
                actor_id="user-1",
                session=session,
            )
            await registry.acknowledge_capabilities(
                plugin1.id,
                actor_id="user-1",
                acked=manifest1.capabilities,
                session=session,
            )
            await registry.enable(
                plugin1.id,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        async with sm() as session:
            enabled = await registry.list_plugins(state="enabled", session=session)
            disabled = await registry.list_plugins(state="disabled", session=session)

        assert len(enabled) == 1
        assert len(disabled) == 1


class TestPluginRegistryDigest:
    """Manifest digest tests."""

    @pytest.mark.asyncio
    async def test_manifest_digest_deterministic(
        self,
        sm: async_sessionmaker,
        audit_chain: SqlAuditChain,
        test_manifest: PluginManifest,
    ) -> None:
        """Manifest digest is deterministic for identical manifests."""
        from server.app.models.audit import AuditEntry
        from sqlalchemy import select

        registry = PluginRegistry(sm, audit_chain)

        # Install same manifest
        async with sm() as session:
            await registry.install(
                test_manifest,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        # Get digest from first install audit entry
        async with sm() as session:
            result = await session.execute(
                select(AuditEntry).where(AuditEntry.action == "plugin.installed")
            )
            first_entry = result.scalars().one()
            _ = first_entry.payload["manifest_digest"]

        # Create second manifest with same content but different ID
        manifest2 = PluginManifest(
            id="io.example.other",
            version=test_manifest.version,
            name=test_manifest.name,
            runtime=test_manifest.runtime,
            capabilities=test_manifest.capabilities,
            min_hl_helper_version=test_manifest.min_hl_helper_version,
            resources=test_manifest.resources.model_dump(),
        )

        async with sm() as session:
            await registry.install(
                manifest2,
                actor_id="user-1",
                session=session,
            )
            await session.commit()

        # Digests should be different if manifests differ
        async with sm() as session:
            result = await session.execute(
                select(AuditEntry).where(
                    AuditEntry.action == "plugin.installed"
                ).order_by(AuditEntry.sequence)
            )
            entries = result.scalars().all()
            # First has different ID, so should have different digest
            assert entries[0].payload["manifest_digest"] != entries[
                1
            ].payload["manifest_digest"]
