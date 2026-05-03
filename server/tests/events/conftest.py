"""Shared pytest fixtures for events tests."""

from __future__ import annotations

# Re-export session maker and engine for events tests
from server.tests.grpc.conftest import (  # noqa: E402, F401
    engine,
    sm,
)
