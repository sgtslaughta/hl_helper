"""Tests for agent logging protobuf message shapes."""

from __future__ import annotations

import pytest


def test_log_entry_fields():
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2 as ab

    msg = ab.LogEntry(
        seq=1, level="info", action="task.exec.completed", category="task", outcome="success"
    )
    assert msg.seq == 1
    assert msg.action == "task.exec.completed"
    assert msg.level == "info"
    assert msg.category == "task"
    assert msg.outcome == "success"


def test_log_batch_contains_entries():
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2 as ab

    batch = ab.LogBatch(first_seq=1, last_seq=2, overflow_flush=False)
    batch.entries.add(seq=1)
    batch.entries.add(seq=2)
    assert len(batch.entries) == 2
    assert batch.first_seq == 1
    assert batch.last_seq == 2


def test_log_policy_default_level():
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2 as ab

    p = ab.LogPolicy(
        policy_version=1,
        default_level="info",
        batch_max_bytes=65536,
        batch_max_interval_s=30,
    )
    assert p.default_level == "info"
    assert p.batch_max_bytes == 65536


def test_heartbeat_has_logs_and_session():
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2 as ab

    hb = ab.Heartbeat(host_id="h", agent_version="0.4.1", agent_session_id="sess-1")
    assert hb.agent_session_id == "sess-1"
    # logs is optional message field
    hb.logs.first_seq = 1
    assert hb.logs.first_seq == 1


def test_heartbeat_ack_has_log_policy():
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2 as ab

    ack = ab.HeartbeatAck(logs_acked_seq=42)
    ack.log_policy.policy_version = 7
    assert ack.log_policy.policy_version == 7


def test_dictionary_ack_shape():
    from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2 as ab

    d = ab.DictionaryAck(version=3, ok=True)
    assert d.ok is True
    assert d.version == 3
