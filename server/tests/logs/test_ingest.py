"""Test agent log ingest pipeline."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from server.app.logs.ingest import ingest_batch
from server.app.logs.models import AgentLog


class FakeBroker:
    def __init__(self):
        self.calls = []

    def publish(self, *, host_id, event):
        self.calls.append({"host_id": host_id, "event": event})


def _entry(seq: int, *, details: dict | None = None, level="info", outcome="success", action="task.exec.completed"):
    doc = {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "ecs.version": "8.11",
        "event": {"kind": "event", "category": ["task"], "action": action, "outcome": outcome, "sequence": seq, "id": f"id-{seq}"},
        "agent": {"id": "a", "type": "hl-agent", "session_id": "s", "version": "0.4.1"},
        "host": {"id": "h", "name": "n"},
        "log": {"level": level, "logger": "agent.task"},
        "labels": {},
        "details": details or {"rc": 0},
    }
    payload = gzip.compress(json.dumps(doc).encode())
    return {"seq": seq, "ts": doc["@timestamp"], "level": level, "action": action, "category": "task", "outcome": outcome, "payload": payload}


def test_ingest_inserts_unique(db_session):
    broker = FakeBroker()
    batch = [_entry(i) for i in range(1, 4)]
    last = ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version="0.4.1", entries=batch, dictionary=None)
    assert last == 3
    rows = db_session.execute(select(AgentLog).order_by(AgentLog.seq)).scalars().all()
    assert [r.seq for r in rows] == [1, 2, 3]


def test_ingest_dedupes_on_session_seq(db_session):
    broker = FakeBroker()
    batch = [_entry(1), _entry(2)]
    ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version=None, entries=batch, dictionary=None)
    ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version=None, entries=batch, dictionary=None)
    rows = db_session.execute(select(AgentLog)).scalars().all()
    assert len(rows) == 2


def test_ingest_redacts_secrets(db_session):
    broker = FakeBroker()
    batch = [_entry(1, details={"raw": "Bearer abc.def-123"})]
    ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version=None, entries=batch, dictionary=None)
    row = db_session.execute(select(AgentLog)).scalar_one()
    assert "abc.def-123" not in json.dumps(row.details)
    # The redaction marker is in the details as a unicode string, check the string directly
    assert "redacted:bearer" in str(row.details)


def test_ingest_broadcasts_to_ws(db_session):
    broker = FakeBroker()
    batch = [_entry(1)]
    ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version=None, entries=batch, dictionary=None)
    assert len(broker.calls) == 1
    assert broker.calls[0]["host_id"] == "h"
    assert broker.calls[0]["event"]["seq"] == 1


def test_ingest_decodes_plain_json(db_session):
    """Entry payload not gzipped (no magic bytes) — accept raw JSON."""
    broker = FakeBroker()
    doc = {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "ecs.version": "8.11",
        "event": {"kind": "event", "category": ["task"], "action": "x", "outcome": "success", "sequence": 1, "id": "i"},
        "agent": {"id": "a", "type": "hl-agent", "session_id": "s"},
        "host": {"id": "h"},
        "log": {"level": "info"},
        "details": {},
        "labels": {},
    }
    entry = {"seq": 1, "ts": doc["@timestamp"], "level": "info", "action": "x", "category": "task", "outcome": "success", "payload": json.dumps(doc).encode()}
    last = ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version=None, entries=[entry], dictionary=None)
    assert last == 1


def test_ingest_resolves_dictionary_ids(db_session):
    broker = FakeBroker()
    doc = {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "ecs.version": "8.11",
        "event": {"kind": "event", "category": ["@id:1"], "action": "@id:2", "outcome": "success", "sequence": 1, "id": "i"},
        "agent": {"id": "a", "type": "hl-agent", "session_id": "s"},
        "host": {"id": "h"},
        "log": {"level": "info"},
    }
    entry = {"seq": 1, "ts": doc["@timestamp"], "level": "info", "action": "task.exec.completed", "category": "task", "outcome": "success", "payload": gzip.compress(json.dumps(doc).encode())}
    ingest_batch(db_session, broker, host_id="h", agent_id="a", agent_session_id="s", agent_version=None, entries=[entry], dictionary={1: "task", 2: "task.exec.completed"})
    row = db_session.execute(select(AgentLog)).scalar_one()
    assert row.action == "task.exec.completed"
    assert row.category == "task"
