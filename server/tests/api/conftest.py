"""Shared pytest fixtures for API tests."""

from __future__ import annotations

import pytest

from server.app.rbac.provider import Principal

# Re-export session maker and signing backend for API tests
from server.tests.grpc.conftest import signing_backend  # noqa: F401
from server.tests.models.conftest import sm  # noqa: F401


@pytest.fixture(autouse=True)
def _setup_default_current_principal_for_approvals_tests(request):
    """Auto-fixture that sets up a default current_principal for approval tests.

    This allows tests that use X-Acting-Principal headers to work without
    explicitly mocking the current_principal dependency in each test.

    Tests can override this by explicitly setting app.dependency_overrides[current_principal].
    """
    # Only apply to approval tests
    if "approvals" not in request.node.nodeid:
        yield
        return

    def patched_current_principal():
        # Return a default authenticated principal
        # Tests that need specific principals will use X-Acting-Principal header
        return Principal(user_id="u-system")

    # Patch the module
    import server.app.deps
    original = server.app.deps.current_principal
    server.app.deps.current_principal = patched_current_principal

    yield

    # Restore
    server.app.deps.current_principal = original
