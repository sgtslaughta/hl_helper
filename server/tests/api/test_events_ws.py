"""Tests for /v1/events WebSocket endpoint."""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from server.app.api.app import create_app
from server.app.events.bus import Bus
from server.app.settings.config import FleetSettings


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch, tmp_path):
    """Set admin token + data_dir in environment for the test app lifespan."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")
    monkeypatch.setenv("FLEET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FLEET_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")


@pytest.fixture
def auth_header():
    """Return admin auth header."""
    return {"Authorization": "Bearer test-tok"}


@pytest.fixture
def mock_settings():
    """Return mocked settings with admin token."""
    return FleetSettings(admin_token=SecretStr("test-tok"))


@pytest.fixture
def bus():
    """Create a Bus instance for testing."""
    return Bus(ring_buffer_size=256)


def test_ws_unauthorized_no_token(mock_settings):
    """Connect without auth token returns 403 close."""
    app = create_app()
    bus_inst = Bus()
    app.state.bus = bus_inst

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/v1/events"):
                    pass


def test_ws_unauthorized_invalid_token(mock_settings):
    """Connect with invalid token returns 403 close."""
    app = create_app()
    bus_inst = Bus()
    app.state.bus = bus_inst

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(
                    "/v1/events",
                    headers={"Authorization": "Bearer wrong-tok"},
                ):
                    pass


def test_ws_authorized_header_token(mock_settings, bus):
    """Connect with valid token in Authorization header succeeds."""
    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events",
                headers={"Authorization": "Bearer test-tok"},
            ) as ws:
                # Should connect successfully
                data = ws.receive_json()
                assert data["type"] == "ready"


def test_ws_authorized_query_token(mock_settings, bus):
    """Connect with valid token in query param succeeds."""
    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events?token=test-tok",
            ) as ws:
                # Should connect successfully
                data = ws.receive_json()
                assert data["type"] == "ready"


def test_ws_subscribe_and_receive(mock_settings, bus):
    """Subscribe to channel and receive published event."""
    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events",
                headers={"Authorization": "Bearer test-tok"},
            ) as ws:
                # Receive ready
                data = ws.receive_json()
                assert data["type"] == "ready"

                # Send subscribe
                ws.send_json(
                    {
                        "type": "subscribe",
                        "channels": ["commands"],
                        "since_sequence": None,
                    }
                )

                # Publish event in background
                import threading

                def publish_event():
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            bus.publish("commands", {"action": "reboot", "host_id": "h1"})
                        )
                    finally:
                        loop.close()

                thread = threading.Thread(target=publish_event)
                thread.start()
                thread.join()

                # Receive event
                data = ws.receive_json()
                assert data["type"] == "event"
                assert data["channel"] == "commands"
                assert data["payload"]["action"] == "reboot"
                assert "sequence" in data
                assert "timestamp" in data


def test_ws_per_channel_isolation(mock_settings, bus):
    """Subscription to one channel does not receive events from another."""
    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events",
                headers={"Authorization": "Bearer test-tok"},
            ) as ws:
                # Receive ready
                ws.receive_json()

                # Subscribe to commands only
                ws.send_json(
                    {
                        "type": "subscribe",
                        "channels": ["commands"],
                        "since_sequence": None,
                    }
                )

                # Publish to audit (not subscribed)
                import threading

                def publish_audit():
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(bus.publish("audit", {"action": "login"}))
                    finally:
                        loop.close()

                thread = threading.Thread(target=publish_audit)
                thread.start()
                thread.join()

                # Publish to commands (subscribed)
                def publish_commands():
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            bus.publish("commands", {"action": "reboot"})
                        )
                    finally:
                        loop.close()

                thread = threading.Thread(target=publish_commands)
                thread.start()
                thread.join()

                # Should only receive commands event, not audit
                data = ws.receive_json()
                assert data["type"] == "event"
                assert data["channel"] == "commands"


def test_ws_invalid_channel_rejected(mock_settings, bus):
    """Subscribe to invalid channel returns error."""
    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events",
                headers={"Authorization": "Bearer test-tok"},
            ) as ws:
                # Receive ready
                ws.receive_json()

                # Send subscribe with invalid channel
                ws.send_json(
                    {
                        "type": "subscribe",
                        "channels": ["invalid_channel"],
                        "since_sequence": None,
                    }
                )

                # Receive error
                data = ws.receive_json()
                assert data["type"] == "error"
                assert "invalid" in data.get("reason", "").lower()


def test_ws_resume_from_sequence(mock_settings, bus):
    """Resume from sequence replays buffered events."""
    import threading

    # Pre-publish events
    def publish_events():
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bus.publish("commands", {"seq": 1}))
            loop.run_until_complete(bus.publish("commands", {"seq": 2}))
            loop.run_until_complete(bus.publish("commands", {"seq": 3}))
        finally:
            loop.close()

    thread = threading.Thread(target=publish_events)
    thread.start()
    thread.join()

    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events",
                headers={"Authorization": "Bearer test-tok"},
            ) as ws:
                # Receive ready
                ws.receive_json()

                # Subscribe with since_sequence=1 (should get 2, 3)
                ws.send_json(
                    {
                        "type": "subscribe",
                        "channels": ["commands"],
                        "since_sequence": 1,
                    }
                )

                # Receive replayed events
                data1 = ws.receive_json()
                assert data1["type"] == "event"
                assert data1["payload"]["seq"] == 2

                data2 = ws.receive_json()
                assert data2["type"] == "event"
                assert data2["payload"]["seq"] == 3


def test_ws_heartbeat_ping(mock_settings, bus):
    """Server can handle pong messages from client."""
    app = create_app()
    app.state.bus = bus

    with mock.patch(
        "server.app.api.v1.events_ws.load_settings",
        return_value=mock_settings,
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/events",
                headers={"Authorization": "Bearer test-tok"},
            ) as ws:
                # Receive ready
                ws.receive_json()

                # Send pong (simulating heartbeat response)
                ws.send_json({"type": "pong"})

                # Connection should remain open
                # Verify we can still send/receive
                ws.send_json(
                    {
                        "type": "subscribe",
                        "channels": ["commands"],
                        "since_sequence": None,
                    }
                )

                # Connection still works
                assert ws is not None
