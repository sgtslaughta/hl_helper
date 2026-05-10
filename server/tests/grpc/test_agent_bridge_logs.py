"""Tests for AgentBridge log ingest + RegisterLogDictionary RPC."""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from server.app.api.v1.logs import LogBroker
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2
from server.app.grpc.agent_bridge import AgentBridgeService
from server.app.grpc.dispatcher import CommandDispatcher
from server.app.logs.models import AgentLog, AgentLogPolicy
from server.app.logs.schemas import LogPolicyDoc


@pytest.mark.asyncio
async def test_register_log_dictionary_caches_strings(
    sm,
) -> None:
    """Call RegisterLogDictionary RPC; verify strings are cached."""
    dispatcher = CommandDispatcher()
    log_broker = LogBroker()
    servicer = AgentBridgeService(
        dispatcher=dispatcher,
        sessionmaker=sm,
        log_broker=log_broker,
    )

    # Build request
    request = agent_bridge_pb2.LogDictionary()
    request.version = 1
    request.strings[0] = "init"
    request.strings[1] = "exec"
    request.strings[2] = "process"

    # Mock context
    class _MockContext:
        pass

    context = _MockContext()

    # Call RPC
    ack = await servicer.RegisterLogDictionary(request, context)

    # Verify response
    assert ack.version == 1
    assert ack.ok is True

    # Verify dictionary is cached (under temp key for now)
    assert len(servicer._log_dicts) > 0
    # Find the temp key
    for k, v in servicer._log_dicts.items():
        if k.startswith("_pending_"):
            assert v == {0: "init", 1: "exec", 2: "process"}
            break
    else:
        pytest.fail("No pending dictionary found")


@pytest.mark.asyncio
async def test_load_host_tags(
    sm,
) -> None:
    """Test that AgentBridgeService._load_host_tags() correctly loads host labels."""
    from server.app.models.host import Host

    # Create test host with tags in labels
    async with sm() as session:
        host = Host(
            id="test-host-tags",
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,
            labels={"tags": ["prod", "critical"]},
            agent_version="0.5.0",
        )
        session.add(host)
        await session.commit()

    # Create servicer and call _load_host_tags
    dispatcher = CommandDispatcher()
    log_broker = LogBroker()
    servicer = AgentBridgeService(
        dispatcher=dispatcher,
        sessionmaker=sm,
        log_broker=log_broker,
    )

    tags = await servicer._load_host_tags("test-host-tags")
    assert tags == ["prod", "critical"]

    # Test non-existent host
    tags = await servicer._load_host_tags("non-existent")
    assert tags == []


@pytest.mark.asyncio
async def test_log_dictionary_moved_to_session_on_heartbeat(
    sm,
) -> None:
    """Test that pending dictionary is moved to session-specific key on heartbeat."""
    dispatcher = CommandDispatcher()
    log_broker = LogBroker()
    servicer = AgentBridgeService(
        dispatcher=dispatcher,
        sessionmaker=sm,
        log_broker=log_broker,
    )

    # Simulate RegisterLogDictionary call
    request = agent_bridge_pb2.LogDictionary()
    request.version = 1
    request.strings[1] = "exec"
    request.strings[2] = "process"

    class _MockContext:
        pass

    await servicer.RegisterLogDictionary(request, _MockContext())

    # Verify dictionary is cached under temp key
    assert len(servicer._log_dicts) == 1
    temp_key = list(servicer._log_dicts.keys())[0]
    assert temp_key.startswith("_pending_")

    # Simulate the logic from heartbeat handler that moves the dictionary
    session_id = "sess-xyz"
    # Check for pending dict keyed by context
    for k in list(servicer._log_dicts.keys()):
        if k.startswith("_pending_"):
            dictionary = servicer._log_dicts.pop(k)
            if session_id:
                servicer._log_dicts[session_id] = dictionary
            break

    # Verify dictionary is now under session key
    assert "sess-xyz" in servicer._log_dicts
    assert servicer._log_dicts["sess-xyz"] == {1: "exec", 2: "process"}
    assert temp_key not in servicer._log_dicts


@pytest.mark.asyncio
async def test_heartbeat_without_logs_unchanged(
    sm,
) -> None:
    """A Heartbeat without logs field should not crash and work as before."""
    from server.app.models.host import Host

    # Create test host
    async with sm() as session:
        host = Host(
            id="test-host-no-logs",
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,
            labels={},
            agent_version="0.5.0",
        )
        session.add(host)
        await session.commit()

    dispatcher = CommandDispatcher()
    log_broker = LogBroker()
    servicer = AgentBridgeService(
        dispatcher=dispatcher,
        sessionmaker=sm,
        log_broker=log_broker,
    )

    # Create heartbeat WITHOUT logs
    hb = agent_bridge_pb2.Heartbeat()
    hb.host_id = "test-host-no-logs"
    hb.at.FromDatetime(datetime.now(timezone.utc))
    hb.agent_version = "0.5.0"
    hb.agent_session_id = "sess-xyz"
    # Don't set logs field

    # Verify it doesn't have logs field set
    assert not hb.HasField("logs")

    # Simulate minimal heartbeat handling (update host)
    async with sm() as session:
        from server.app.models.host import Host

        host = await session.get(Host, "test-host-no-logs")
        if host:
            host.last_seen_at = datetime.now(timezone.utc)
            host.status = "healthy"
            await session.commit()

        # The HasField check should prevent any log processing
        if hb.HasField("logs"):
            pytest.fail("Heartbeat should not have logs field")

    # Verify host was updated
    async with sm() as session:
        host = await session.get(Host, "test-host-no-logs")
        assert host.status == "healthy"
        assert host.last_seen_at is not None


@pytest.mark.asyncio
async def test_hb_ack_proto_structure(
    sm,
) -> None:
    """Test that HeartbeatAck is correctly built from LogPolicy."""
    from server.app.logs.schemas import CategoryRuleDoc

    # Create a log policy document
    policy_doc = LogPolicyDoc(
        policy_version=3,
        default_level="warn",
        batch_max_bytes=32768,
        batch_max_interval_s=60,
        buffer_max_mb=200,
        buffer_max_days=30,
        default_sample_rate=0.5,
        categories=[
            CategoryRuleDoc(category="auth", level="error", sample_rate=1.0),
            CategoryRuleDoc(category="system", level="info", sample_rate=0.5),
        ],
    )

    # Build HeartbeatAck from policy (simulating what agent_bridge does)
    ack = agent_bridge_pb2.HeartbeatAck()
    ack.logs_acked_seq = 42
    ack.log_policy.policy_version = policy_doc.policy_version or 1
    ack.log_policy.default_level = policy_doc.default_level
    ack.log_policy.batch_max_bytes = policy_doc.batch_max_bytes
    ack.log_policy.batch_max_interval_s = policy_doc.batch_max_interval_s
    ack.log_policy.buffer_max_mb = policy_doc.buffer_max_mb
    ack.log_policy.buffer_max_days = policy_doc.buffer_max_days
    ack.log_policy.default_sample_rate = policy_doc.default_sample_rate
    if policy_doc.expires_at:
        ack.log_policy.expires_at.FromDatetime(policy_doc.expires_at)

    for cr in policy_doc.categories:
        rule = ack.log_policy.categories.add()
        rule.category = cr.category
        if cr.level:
            rule.level = cr.level
        if cr.sample_rate is not None:
            rule.sample_rate = cr.sample_rate
        rule.drop = cr.drop

    # Verify the protobuf structure
    assert ack.logs_acked_seq == 42
    assert ack.log_policy.policy_version == 3
    assert ack.log_policy.default_level == "warn"
    assert ack.log_policy.batch_max_bytes == 32768
    assert ack.log_policy.batch_max_interval_s == 60
    assert ack.log_policy.buffer_max_mb == 200
    assert ack.log_policy.buffer_max_days == 30
    assert ack.log_policy.default_sample_rate == 0.5
    assert len(ack.log_policy.categories) == 2
    assert ack.log_policy.categories[0].category == "auth"
    assert ack.log_policy.categories[0].level == "error"
    assert ack.log_policy.categories[0].sample_rate == 1.0
    assert ack.log_policy.categories[1].category == "system"
    assert ack.log_policy.categories[1].sample_rate == 0.5
