"""Pydantic schemas for ECS events and log policies."""

from __future__ import annotations

import fnmatch
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Event(BaseModel):
    """Elastic Common Schema event metadata."""

    kind: str = "event"
    category: list[str] = Field(default_factory=list)
    type: list[str] = Field(default_factory=list)
    action: str
    outcome: str | None = None
    duration: int | None = None
    sequence: int
    id: str


class _Agent(BaseModel):
    """Agent metadata."""

    id: str
    version: str | None = None
    type: str = "hl-agent"
    session_id: str


class _Host(BaseModel):
    """Host metadata."""

    id: str
    name: str | None = None


class _Log(BaseModel):
    """Logging metadata."""

    level: str
    logger: str | None = None


class _Error(BaseModel):
    """Error details."""

    code: str | None = None
    message: str | None = None
    stack_trace: str | None = None


class ECSEvent(BaseModel):
    """Elastic Common Schema event from an agent."""

    model_config = ConfigDict(populate_by_name=True)

    ts: datetime = Field(alias="@timestamp")
    ecs_version: str = Field(alias="ecs.version", default="8.11")
    event: _Event
    agent: _Agent
    host: _Host
    log: _Log
    labels: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    error: _Error | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CategoryRuleDoc(BaseModel):
    """Rule for categorizing and filtering log entries."""

    category: str
    level: str | None = None
    sample_rate: float | None = None
    drop: bool = False

    def matches(self, name: str) -> bool:
        """Check if category pattern matches a log category name."""
        return fnmatch.fnmatchcase(name, self.category)


class LogPolicyDoc(BaseModel):
    """Policy configuration for agent log collection."""

    policy_version: int = 1
    default_level: str = "info"
    batch_max_bytes: int = 65536
    batch_max_interval_s: int = 30
    buffer_max_mb: int = 50
    buffer_max_days: int = 7
    default_sample_rate: float = 1.0
    categories: list[CategoryRuleDoc] = Field(default_factory=list)
    expires_at: datetime | None = None
    backoff_ms: int = 0
