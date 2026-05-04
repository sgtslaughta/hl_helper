"""Tests for Bus singleton wiring in lifespan."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from server.app.dispatcher.dispatcher import RebootPayload
from server.app.events.bus import Bus
from server.app.lifespan import build_app_state
from server.app.rbac.provider import Principal
from server.app.settings.config import FleetSettings


@pytest.mark.asyncio
async def test_bus_is_shared_across_components() -> None:
    """Bus instance is shared by api_dispatcher, audit_chain, and result_handler."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
            allow_permissive_rbac=True,
        )

        state = await build_app_state(settings)

        # Verify bus exists on state
        assert isinstance(state.bus, Bus)

        # Verify all components share the same bus instance
        assert state.bus is state.api_dispatcher._event_bus
        assert state.bus is state.audit_chain._event_bus
        assert state.bus is state.result_handler._event_bus


@pytest.mark.asyncio
async def test_dispatcher_publishes_to_shared_bus() -> None:
    """Command dispatch publishes events to the shared bus."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
            allow_permissive_rbac=True,
        )

        state = await build_app_state(settings)

        # Subscribe to commands channel
        sub = state.bus.subscribe("commands")

        # Dispatch a low-risk shell command to a test host
        async with state.sessionmaker() as session:
            from server.app.models.host import Host
            from server.app.dispatcher.targets import HostListSelector

            # Create a test host
            test_host = Host(
                id="test-host-1",
                hostname="test.example.com",
                agent_pubkey=b"\x00" * 32,
            )
            session.add(test_host)
            await session.flush()

            principal = Principal(user_id="test-user")
            targets = HostListSelector(host_ids=["test-host-1"])
            payload = RebootPayload(reason="bus-wiring test")

            # Dispatch the command
            await state.api_dispatcher.dispatch(
                session,
                principal=principal,
                targets=targets,
                payload=payload,
            )

            await session.commit()

        # Give asyncio tasks a chance to execute
        await asyncio.sleep(0.1)

        # Check if command event was published to the bus
        try:
            event = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            assert event.channel == "commands"
            assert "command.issued" in str(event.payload)
        except asyncio.TimeoutError:
            pytest.fail("No command event received on the bus")
        finally:
            await sub.close()
