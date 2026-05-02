"""Shared pytest fixtures for search tests."""

from __future__ import annotations

# Re-export session maker and engine for search tests
from server.tests.grpc.conftest import (  # noqa: E402, F401
    engine,
    sm,
)
