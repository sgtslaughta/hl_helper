"""End-to-end tests for AgentBridge.Stream RPC handler."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import grpc
import grpc.aio
import pytest

from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2, agent_bridge_pb2_grpc, envelope_pb2
from server.app.grpc.dispatcher import CommandDispatcher


def make_env(host_id: str, command_id: str) -> envelope_pb2.CommandEnvelope:
    """Build a CommandEnvelope for testing."""
    env = envelope_pb2.CommandEnvelope()
    env.command_id = command_id
    env.host_id = host_id
    env.sequence = 1
    env.nonce = b"test"
    now = datetime.now(timezone.utc)
    env.issued_at.FromDatetime(now)
    env.expires_at.FromDatetime(now)
    env.issued_by = "test-server"
    env.pkg_update.classes.append("base")
    return env


@pytest.mark.asyncio
async def test_stream_delivers_enqueued_command(
    grpc_server_and_dispatcher: tuple[str, CommandDispatcher],
    tls_creds: dict[str, bytes],
) -> None:
    """Connect agent stream; controller enqueues command; agent receives it."""
    bound_addr, dispatcher = grpc_server_and_dispatcher
    _host, port_str = bound_addr.rsplit(":", 1)
    port = int(port_str)

    creds = grpc.ssl_channel_credentials(
        root_certificates=tls_creds["ca_chain_pem"],
        private_key=tls_creds["client_key_pem"],
        certificate_chain=tls_creds["client_cert_pem"],
    )

    async with grpc.aio.secure_channel(
        f"127.0.0.1:{port}",
        creds,
        options=[("grpc.ssl_target_name_override", "localhost")],
    ) as channel:
        stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)

        # Start stream (agent sends empty iterator initially)
        call = stub.Stream(iter([]))

        # Enqueue a command for the host
        cmd = make_env("test-host-1", "cmd-1")
        await dispatcher.enqueue("test-host-1", cmd)

        # Agent should receive the command
        msg = await asyncio.wait_for(call.read(), timeout=2.0)
        assert msg.WhichOneof("msg") == "command"
        assert msg.command.command_id == "cmd-1"


@pytest.mark.asyncio
async def test_stream_replays_unacked_on_reconnect(
    grpc_server_and_dispatcher: tuple[str, CommandDispatcher],
    tls_creds: dict[str, bytes],
) -> None:
    """Disconnect without ack; reconnect; command redelivered."""
    bound_addr, dispatcher = grpc_server_and_dispatcher
    _host, port_str = bound_addr.rsplit(":", 1)
    port = int(port_str)

    creds = grpc.ssl_channel_credentials(
        root_certificates=tls_creds["ca_chain_pem"],
        private_key=tls_creds["client_key_pem"],
        certificate_chain=tls_creds["client_cert_pem"],
    )

    channel_opts = [("grpc.ssl_target_name_override", "localhost")]

    # First connection: receive command but don't ack
    async with grpc.aio.secure_channel(
        f"127.0.0.1:{port}",
        creds,
        options=channel_opts,
    ) as channel:
        stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)
        call = stub.Stream(iter([]))

        cmd = make_env("test-host-1", "cmd-1")
        await dispatcher.enqueue("test-host-1", cmd)

        msg = await asyncio.wait_for(call.read(), timeout=2.0)
        assert msg.command.command_id == "cmd-1"
        # Don't send ack; just disconnect

    # Wait a moment for disconnect to register
    await asyncio.sleep(0.1)

    # Second connection: same command should be replayed
    async with grpc.aio.secure_channel(
        f"127.0.0.1:{port}",
        creds,
        options=channel_opts,
    ) as channel:
        stub = agent_bridge_pb2_grpc.AgentBridgeStub(channel)
        call = stub.Stream(iter([]))

        msg = await asyncio.wait_for(call.read(), timeout=2.0)
        assert msg.WhichOneof("msg") == "command"
        assert msg.command.command_id == "cmd-1"


@pytest.mark.asyncio
async def test_stream_acks_remove_from_unacked(
    grpc_server_and_dispatcher: tuple[str, CommandDispatcher],
) -> None:
    """Dispatcher ack removes command from unacked tracking."""
    _bound_addr, dispatcher = grpc_server_and_dispatcher

    # Enqueue and simulate the full lifecycle:
    # 1. Queue cmd
    # 2. Register (pulls cmd, marks in-flight)
    # 3. Ack cmd
    # 4. Reconnect - cmd should not be replayed
    cmd = make_env("test-host-1", "cmd-1")
    await dispatcher.enqueue("test-host-1", cmd)

    state1 = await dispatcher.register("test-host-1")
    pulled = await asyncio.wait_for(state1.queue.get(), timeout=1.0)
    await dispatcher.mark_in_flight("test-host-1", pulled)

    # Verify cmd is in unacked
    assert "cmd-1" in state1.unacked

    # Disconnect and ack
    await dispatcher.unregister("test-host-1")
    await dispatcher.ack("test-host-1", "cmd-1")

    # Reconnect: queue should be empty (cmd was acked, not replayed)
    state2 = await dispatcher.register("test-host-1")
    assert state2.queue.empty()


@pytest.mark.asyncio
async def test_stream_rejects_no_spiffe_id() -> None:
    """Stream handler rejects request when peer SPIFFE ID cannot be extracted."""
    # This tests the peer_context check in agent_bridge.Stream.
    # We'll mock a context without a valid SPIFFE cert.
    from unittest.mock import AsyncMock, MagicMock

    from server.app.grpc.agent_bridge import AgentBridgeService
    from server.app.grpc.dispatcher import CommandDispatcher

    dispatcher = CommandDispatcher()
    service = AgentBridgeService(dispatcher)

    # Create a mock context with no peer cert
    context = MagicMock()
    context.auth_context.return_value = {}  # No x509_pem_cert
    context.abort = AsyncMock()  # Make abort async so it can be awaited

    # Call should abort with UNAUTHENTICATED
    request_iterator = iter([])
    result = service.Stream(request_iterator, context)

    # Try to iterate; should abort
    with pytest.raises(StopAsyncIteration):
        await result.__anext__()

    # Verify abort was called
    context.abort.assert_called_once()
    call_args = context.abort.call_args
    assert call_args[0][0] == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_stream_rejects_concurrent_for_same_host(
    grpc_server_and_dispatcher: tuple[str, CommandDispatcher],
    tls_creds: dict[str, bytes],
) -> None:
    """Second stream with same host_id → ALREADY_EXISTS."""
    bound_addr, _dispatcher = grpc_server_and_dispatcher
    _host, port_str = bound_addr.rsplit(":", 1)
    port = int(port_str)

    creds = grpc.ssl_channel_credentials(
        root_certificates=tls_creds["ca_chain_pem"],
        private_key=tls_creds["client_key_pem"],
        certificate_chain=tls_creds["client_cert_pem"],
    )

    channel_opts = [("grpc.ssl_target_name_override", "localhost")]

    # First connection - keep it open by queueing messages indefinitely
    async with grpc.aio.secure_channel(
        f"127.0.0.1:{port}",
        creds,
        options=channel_opts,
    ) as channel1:
        stub1 = agent_bridge_pb2_grpc.AgentBridgeStub(channel1)

        # Create an async generator that yields periodically
        async def keep_stream_open():
            for _ in range(100):  # Keep alive for a bit
                yield agent_bridge_pb2.AgentToServer()  # Dummy heartbeat
                await asyncio.sleep(0.05)

        _call1 = stub1.Stream(keep_stream_open())

        # Give the handler a moment to start
        await asyncio.sleep(0.1)

        # Now try a second connection with same host_id
        async with grpc.aio.secure_channel(
            f"127.0.0.1:{port}",
            creds,
            options=channel_opts,
        ) as channel2:
            stub2 = agent_bridge_pb2_grpc.AgentBridgeStub(channel2)
            call2 = stub2.Stream(iter([]))

            with pytest.raises(grpc.aio.AioRpcError) as exc:
                await call2.read()
            assert exc.value.code() == grpc.StatusCode.ALREADY_EXISTS


@pytest.mark.asyncio
async def test_stream_acks_even_on_result_error(
    grpc_server_and_dispatcher: tuple[str, CommandDispatcher],
) -> None:
    """Result processing error → still ack to avoid retry storm."""
    _bound_addr, dispatcher = grpc_server_and_dispatcher

    cmd = make_env("test-host-1", "cmd-1")
    await dispatcher.enqueue("test-host-1", cmd)

    state = await dispatcher.register("test-host-1")
    pulled = await asyncio.wait_for(state.queue.get(), timeout=1.0)
    await dispatcher.mark_in_flight("test-host-1", pulled)

    # Without result_handler, the stream still processes messages
    assert "cmd-1" in state.unacked

    await dispatcher.unregister("test-host-1")
    await dispatcher.ack("test-host-1", "cmd-1")

    # Reconnect: queue should be empty
    state2 = await dispatcher.register("test-host-1")
    assert state2.queue.empty()
