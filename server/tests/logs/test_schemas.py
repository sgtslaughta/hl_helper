"""Test Pydantic schemas for ECS events and log policies."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from server.app.logs.schemas import ECSEvent, LogPolicyDoc, CategoryRuleDoc


def test_ecs_event_roundtrip() -> None:
    """Validate ECS event parsing from raw dict with all expected fields."""
    raw = {
        "@timestamp": "2026-05-10T22:15:03.412Z",
        "ecs.version": "8.11",
        "event": {
            "kind": "event",
            "action": "task.exec.completed",
            "category": ["task"],
            "outcome": "success",
            "sequence": 1,
            "id": "01HXY",
        },
        "agent": {
            "id": "a",
            "version": "0.4.1",
            "type": "hl-agent",
            "session_id": "s",
        },
        "host": {"id": "h", "name": "n"},
        "log": {"level": "info", "logger": "agent.task"},
        "message": "ok",
        "labels": {"k": "v"},
        "details": {"rc": 0},
    }
    ev = ECSEvent.model_validate(raw)
    assert ev.event.outcome == "success"
    assert ev.agent.session_id == "s"
    assert ev.event.sequence == 1
    assert ev.labels["k"] == "v"
    assert ev.message == "ok"


def test_ecs_event_requires_session_id() -> None:
    """Validate that agent.session_id is required."""
    raw = {
        "@timestamp": "2026-05-10T22:15:03.412Z",
        "event": {
            "action": "x",
            "category": ["task"],
            "sequence": 1,
            "id": "i",
        },
        "agent": {"id": "a", "type": "hl-agent"},
        "host": {"id": "h"},
        "log": {"level": "info"},
    }
    with pytest.raises(ValidationError):
        ECSEvent.model_validate(raw)


def test_policy_doc_defaults() -> None:
    """Validate LogPolicyDoc defaults."""
    p = LogPolicyDoc(default_level="info")
    assert p.batch_max_bytes == 65536
    assert p.batch_max_interval_s == 30
    assert p.buffer_max_mb == 50
    assert p.buffer_max_days == 7
    assert p.default_sample_rate == 1.0


def test_category_rule_glob() -> None:
    """Validate CategoryRuleDoc glob matching."""
    r = CategoryRuleDoc(category="plugin.*", level="debug", sample_rate=0.5)
    assert r.matches("plugin.docker")
    assert r.matches("plugin.acme.scan")
    assert not r.matches("task.exec.completed")


def test_category_rule_exact() -> None:
    """Validate CategoryRuleDoc exact matching when no wildcards."""
    r = CategoryRuleDoc(category="task", drop=True)
    assert r.matches("task")
    assert not r.matches("task.exec")
