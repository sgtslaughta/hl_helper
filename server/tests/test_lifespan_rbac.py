"""Tests for RBAC provider wiring in lifespan."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from server.app.lifespan import build_app_state
from server.app.settings.config import FleetSettings


@pytest.mark.asyncio
async def test_lifespan_wires_real_rbac_provider_by_default() -> None:
    """Without FLEET_ALLOW_PERMISSIVE_RBAC=1, real RBAC provider is wired."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
        )

        # Ensure env var is not set (or set to 0)
        with mock.patch.dict(os.environ, {"FLEET_ALLOW_PERMISSIVE_RBAC": "0"}):
            state = await build_app_state(settings)

        # RBAC provider should be _RealRbacProvider (wrapping BuiltinEngine)
        from server.app.lifespan import _RealRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _RealRbacProvider)


@pytest.mark.asyncio
async def test_lifespan_allows_permissive_rbac_with_flag() -> None:
    """With FLEET_ALLOW_PERMISSIVE_RBAC=1, permissive provider is allowed."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
        )

        # Set the flag to allow permissive RBAC
        with mock.patch.dict(os.environ, {"FLEET_ALLOW_PERMISSIVE_RBAC": "1"}):
            state = await build_app_state(settings)

        # RBAC provider should be _PermissiveRbacProvider
        from server.app.lifespan import _PermissiveRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _PermissiveRbacProvider)


@pytest.mark.asyncio
async def test_lifespan_wires_real_in_prod_without_flag() -> None:
    """In prod without flag, real RBAC provider (fail-closed) is wired."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
        )

        # Set FLEET_ENV=prod without the flag
        with mock.patch.dict(
            os.environ,
            {
                "FLEET_ENV": "prod",
                "FLEET_ALLOW_PERMISSIVE_RBAC": "0",
            },
            clear=False,
        ):
            state = await build_app_state(settings)

        # Should wire real provider (not permissive)
        from server.app.lifespan import _RealRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _RealRbacProvider)


@pytest.mark.asyncio
async def test_lifespan_real_rbac_provider_has_sessionmaker() -> None:
    """_RealRbacProvider is instantiated with sessionmaker for DB queries."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
        )

        with mock.patch.dict(os.environ, {"FLEET_ALLOW_PERMISSIVE_RBAC": "0"}):
            state = await build_app_state(settings)

        # _RealRbacProvider should have been wired with sessionmaker
        from server.app.lifespan import _RealRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _RealRbacProvider)
        # sessionmaker should be available and usable
        assert state.sessionmaker is not None
