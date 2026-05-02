"""Shared pytest fixtures for RBAC tests."""

from __future__ import annotations

# Re-export session maker and engine for approval engine tests
from server.tests.grpc.conftest import (  # noqa: E402, F401
    engine,
    sm,
)
