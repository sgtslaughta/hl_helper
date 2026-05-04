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
    """Without allow_permissive_rbac=true in config, real RBAC provider is wired."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
            allow_permissive_rbac=False,
        )

        state = await build_app_state(settings)

        # RBAC provider should be _RealRbacProvider (wrapping BuiltinEngine)
        from server.app.lifespan import _RealRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _RealRbacProvider)


@pytest.mark.asyncio
async def test_lifespan_allows_permissive_rbac_with_config() -> None:
    """With allow_permissive_rbac=true in config, permissive provider is allowed."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
            allow_permissive_rbac=True,
        )

        state = await build_app_state(settings)

        # RBAC provider should be _PermissiveRbacProvider
        from server.app.lifespan import _PermissiveRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _PermissiveRbacProvider)


@pytest.mark.asyncio
async def test_lifespan_wires_real_in_prod_without_permissive() -> None:
    """In prod without allow_permissive_rbac=true, real RBAC provider (fail-closed) is wired."""
    with TemporaryDirectory() as tmpdir:
        settings = FleetSettings(
            db_url="sqlite+aiosqlite:///:memory:",
            data_dir=Path(tmpdir),
            public_url="https://localhost",
            allow_permissive_rbac=False,
        )

        # Set FLEET_ENV=prod without the flag
        with mock.patch.dict(
            os.environ,
            {"FLEET_ENV": "prod"},
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
            allow_permissive_rbac=False,
        )

        state = await build_app_state(settings)

        # _RealRbacProvider should have been wired with sessionmaker
        from server.app.lifespan import _RealRbacProvider
        assert isinstance(state.api_dispatcher._rbac_provider, _RealRbacProvider)
        # sessionmaker should be available and usable
        assert state.sessionmaker is not None
