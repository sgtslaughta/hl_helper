"""WebSocket endpoint for real-time event streaming."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from server.app.api.state import get_app_state
from server.app.events.bus import Bus, Event
from server.app.events.ws_filter import event_visible
from server.app.settings.config import load_settings

router = APIRouter(prefix="/v1", tags=["events"])

# Allowed channels for subscription
ALLOWED_CHANNELS = {"commands", "audit", "hosts.status"}
BACKPRESSURE_CHANNELS = {
    "_backpressure.commands",
    "_backpressure.audit",
    "_backpressure.hosts.status",
}


def _validate_channels(channels: list[str]) -> bool:
    """Validate channel names against allowlist.

    Args:
        channels: List of channel names.

    Returns:
        True if all channels are in allowlist, False otherwise.
    """
    valid = ALLOWED_CHANNELS | BACKPRESSURE_CHANNELS
    return all(ch in valid for ch in channels)


def _verify_ws_auth(ws: WebSocket, token_query: str | None) -> str | None:
    """Verify WebSocket auth from Authorization header or query param.

    Args:
        ws: FastAPI WebSocket (carries headers + query_params on the upgrade).
        token_query: Token from ?token= query param.

    Returns:
        Principal string ("admin") if authenticated, None otherwise.
    """
    settings = load_settings()
    if settings.admin_token is None:
        return None

    admin_token = settings.admin_token.get_secret_value()

    # Check Authorization header first
    auth_header = ws.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Use constant-time comparison
        if secrets.compare_digest(token, admin_token):
            return "admin"

    # Check query param
    if token_query:
        if secrets.compare_digest(token_query, admin_token):
            return "admin"

    return None


async def _event_to_json(event: Event) -> dict[str, Any]:
    """Convert Event to JSON-serializable dict."""
    return {
        "type": "event",
        "sequence": event.sequence,
        "channel": event.channel,
        "payload": dict(event.payload),
        "timestamp": event.timestamp.isoformat(),
    }


async def _send_heartbeat(
    ws: WebSocket,
    last_pong: dict[str, float],
    interval_sec: float,
    timeout_sec: float,
) -> None:
    """Send periodic ping frames; close ws when pong-timeout exceeded.

    `last_pong` is a 1-element dict {"ts": float} mutated by the main loop on
    each pong. When `now - last_pong > timeout_sec` we close 1011 and exit.
    """
    import time

    while True:
        try:
            await asyncio.sleep(interval_sec)
            if time.monotonic() - last_pong["ts"] > timeout_sec:
                try:
                    await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason="pong-timeout")
                except Exception:
                    pass
                return
            await ws.send_json({"type": "ping"})
        except (WebSocketDisconnect, RuntimeError):
            return


@router.websocket("/events")
async def events_ws(
    ws: WebSocket,
    token: str | None = Query(None),
    heartbeat_interval: float = 30.0,
    pong_timeout: float = 60.0,
) -> None:
    """WebSocket endpoint for real-time event streaming.

    Path: /v1/events

    Query params:
        token: Optional admin token (alternative to Authorization header).

    Authorization:
        Accepts Authorization: Bearer <token> header OR ?token=<token> query param.

    Client messages:
        - {"type": "subscribe", "channels": [...], "since_sequence": <int|null>}

    Server responses:
        - {"type": "ready"}: Connection established, ready for subscribe.
        - {"type": "event", "sequence": ..., "channel": ..., "payload": ..., "timestamp": ...}
        - {"type": "ping"}: Heartbeat (client should respond with pong).
        - {"type": "error", "reason": ...}: Validation error.

    Behavior:
        1. On connect: validate auth → send ready or close 1008.
        2. Client sends subscribe with channel list and optional since_sequence.
        3. Server validates channels (allowlist), creates subscriptions.
        4. Server sends matching events as they're published; filters by RBAC.
        5. Heartbeat every 30s; close with 1011 if no pong within 60s.
        6. On disconnect: close all subscriptions.
    """
    # Verify auth
    principal = _verify_ws_auth(ws, token)
    if principal is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="unauthorized")
        return

    # Accept connection
    await ws.accept()

    # Resolve Bus. Tests that inject ``app.state.bus = bus_inst`` directly
    # take precedence over the lifespan-built bus (legacy injection path).
    # Fall back to lifespan's bus, then to a fresh Bus.
    direct_bus = getattr(ws.app.state, "bus", None)
    if isinstance(direct_bus, Bus):
        bus = direct_bus
    else:
        state = get_app_state(ws)
        bus = state.bus if state.bus is not None else Bus()
        if direct_bus is None:
            ws.app.state.bus = bus

    # Send ready signal
    await ws.send_json({"type": "ready"})

    # Track subscriptions and forwarding tasks
    import time
    subscriptions: dict[str, Any] = {}
    forward_tasks: list[asyncio.Task[Any]] = []
    last_pong: dict[str, float] = {"ts": time.monotonic()}
    heartbeat_task = asyncio.create_task(
        _send_heartbeat(ws, last_pong, heartbeat_interval, pong_timeout)
    )

    try:
        while True:
            # Receive message from client
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except RuntimeError:
                break

            msg_type = data.get("type")

            if msg_type == "subscribe":
                # Validate channels
                channels = data.get("channels", [])
                if not isinstance(channels, list) or not _validate_channels(channels):
                    await ws.send_json(
                        {
                            "type": "error",
                            "reason": f"invalid channels; allowed: {sorted(ALLOWED_CHANNELS | BACKPRESSURE_CHANNELS)}",
                        }
                    )
                    continue

                since_sequence = data.get("since_sequence")

                # Create subscriptions per channel
                for channel in channels:
                    if channel not in subscriptions:
                        sub = bus.subscribe(
                            channel,
                            since_sequence=since_sequence,
                            max_queue=1024,
                        )
                        subscriptions[channel] = sub

                        # Create forwarding task for this channel (capture sub in closure)
                        async def forward_events(sub: Any = sub) -> None:
                            """Forward events from subscription to client."""
                            try:
                                async for event in sub:
                                    # Apply RBAC filter
                                    if not event_visible(principal, event):
                                        continue
                                    # Send event as JSON
                                    msg = await _event_to_json(event)
                                    await ws.send_json(msg)
                            except (WebSocketDisconnect, RuntimeError):
                                pass
                            except Exception:
                                # Silently exit on other errors
                                pass

                        task = asyncio.create_task(forward_events())
                        forward_tasks.append(task)

            elif msg_type == "pong":
                # Heartbeat response received — record timestamp
                last_pong["ts"] = time.monotonic()

            else:
                # Unknown message type
                await ws.send_json(
                    {
                        "type": "error",
                        "reason": f"unknown message type: {msg_type}",
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        # Cancel heartbeat
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except (asyncio.CancelledError, Exception):
            pass

        # Close all subscriptions
        for sub in subscriptions.values():
            await sub.close()

        # Cancel forwarding tasks
        for task in forward_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
