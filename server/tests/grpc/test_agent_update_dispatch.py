"""Tests for agent update dispatch and heartbeat persistence."""

from __future__ import annotations

from uuid import uuid4

import pytest

from server.app.grpc.agent_bridge import _build_agent_update_cmd, _persist_heartbeat
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2, commands_pb2
from server.app.models.host import Host, AgentUpdateStatus


@pytest.mark.asyncio
async def test_build_agent_update_cmd_signs_token(sm, host_id, published_release_id):
    """Test _build_agent_update_cmd creates AgentUpdateCmd with download token."""
    payload = {"release_id": published_release_id, "force": False}
    async with sm() as session:
        cmd = await _build_agent_update_cmd(
            payload, host_id=host_id, session=session, public_url="http://localhost:8000"
        )
    assert isinstance(cmd, commands_pb2.AgentUpdateCmd)
    assert cmd.release_id == published_release_id
    assert cmd.expected_sha256 == "abc123def456"
    assert cmd.manifest_json == b'{"version":"0.4.1"}'
    assert cmd.manifest_sig == b"sig"
    assert cmd.download_token
    assert cmd.binary_url == f"http://localhost:8000/v1/agent-releases/{published_release_id}/binary"
    assert cmd.expected_size == 1024
    assert cmd.force is False


@pytest.mark.asyncio
async def test_build_agent_update_cmd_force_flag(sm, host_id, published_release_id):
    """Test _build_agent_update_cmd respects force flag."""
    payload = {"release_id": published_release_id, "force": True}
    async with sm() as session:
        cmd = await _build_agent_update_cmd(
            payload, host_id=host_id, session=session, public_url="http://localhost:8000"
        )
    assert cmd.force is True


@pytest.mark.asyncio
async def test_persist_heartbeat_updates_version_and_status(sm, host_id):
    """Test _persist_heartbeat updates agent version and update status."""
    hb = agent_bridge_pb2.Heartbeat(
        agent_version="0.4.2",
        update_status=agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_HEALTHCHECKING,
        update_target_version="0.4.2",
    )
    async with sm() as session:
        await _persist_heartbeat(session, host_id, hb)
        # Refresh the host to get updated values
        host = await session.get(Host, host_id)
        assert host.agent_version == "0.4.2"
        assert host.agent_update_status == AgentUpdateStatus.HEALTHCHECKING
        assert host.agent_update_target_version == "0.4.2"


@pytest.mark.asyncio
async def test_persist_heartbeat_idle_status(sm, host_id):
    """Test _persist_heartbeat with IDLE status."""
    hb = agent_bridge_pb2.Heartbeat(
        agent_version="0.4.1",
        update_status=agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_IDLE,
    )
    async with sm() as session:
        await _persist_heartbeat(session, host_id, hb)
        host = await session.get(Host, host_id)
        assert host.agent_version == "0.4.1"
        assert host.agent_update_status == AgentUpdateStatus.IDLE


@pytest.mark.asyncio
async def test_persist_heartbeat_downloading_status(sm, host_id):
    """Test _persist_heartbeat with DOWNLOADING status."""
    hb = agent_bridge_pb2.Heartbeat(
        agent_version="0.4.0",
        update_status=agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_DOWNLOADING,
        update_target_version="0.4.1",
    )
    async with sm() as session:
        await _persist_heartbeat(session, host_id, hb)
        host = await session.get(Host, host_id)
        assert host.agent_version == "0.4.0"
        assert host.agent_update_status == AgentUpdateStatus.DOWNLOADING
        assert host.agent_update_target_version == "0.4.1"


@pytest.mark.asyncio
async def test_persist_heartbeat_nonexistent_host(sm):
    """Test _persist_heartbeat gracefully handles nonexistent host."""
    fake_host_id = str(uuid4())
    hb = agent_bridge_pb2.Heartbeat(
        agent_version="0.4.2",
        update_status=agent_bridge_pb2.Heartbeat.AgentUpdateStatus.AGENT_UPDATE_STATUS_IDLE,
    )
    async with sm() as session:
        # Should not raise
        await _persist_heartbeat(session, fake_host_id, hb)
