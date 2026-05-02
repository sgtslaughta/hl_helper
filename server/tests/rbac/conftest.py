"""Shared pytest fixtures for RBAC tests."""

from __future__ import annotations

# Re-export session maker and engine for approval engine tests
from server.tests.grpc.conftest import (  # noqa: E402, F401
    engine,
)

# Import the seed fixture which will auto-populate built-in roles
from server.tests.models.conftest import (  # noqa: E402, F401
    sm,
)
