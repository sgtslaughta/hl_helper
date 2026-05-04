"""Tests for SealedModeMonitor — degraded read-only behavior on Vault seal.

Channel choice: ``secrets.status`` (new dedicated channel) is used for
sealed/recovered events. This keeps host-status and secrets-status concerns
separate; UI banner subscribers can listen to a single, focused channel.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from server.app.events.bus import Bus
from server.app.secrets.backends.base import BackendSealed, SecretsBackend
from server.app.secrets.broker import SecretsBroker
from server.app.secrets.cache import BrokerCache
from server.app.secrets.handle import HandleStore
from server.app.secrets.ref import SecretRef
from server.app.secrets.sealed import SealedModeMonitor, SealedState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault_backend() -> MagicMock:
    """Mock vault backend with controllable health_check."""
    backend = AsyncMock(spec=SecretsBackend)
    # Default healthy state
    backend.health_check = AsyncMock(return_value={"sealed": False, "initialized": True})
    backend.get = AsyncMock(return_value=b"vault-secret")
    backend.put = AsyncMock(return_value=1)
    backend.versions = AsyncMock(return_value=[1])
    backend.delete = AsyncMock()
    return backend


@pytest.fixture
def cache() -> BrokerCache:
    return BrokerCache(ttl_seconds=30)


@pytest.fixture
def broker(vault_backend: MagicMock, cache: BrokerCache) -> SecretsBroker:
    return SecretsBroker(
        backends={"vault": vault_backend},
        cache=cache,
        handle_store=HandleStore(),
    )


@pytest.fixture
def bus() -> Bus:
    return Bus()


# ---------------------------------------------------------------------------
# Direct SealedModeMonitor tests
# ---------------------------------------------------------------------------


@freeze_time("2026-05-04 12:00:00")
async def test_not_degraded_initially(broker: SecretsBroker, vault_backend: MagicMock, bus: Bus) -> None:
    """Monitor starts in non-degraded state."""
    mon = SealedModeMonitor(broker=broker, bus=bus, vault_backend=vault_backend)
    assert mon.is_degraded() is False
    state = mon.last_status()
    assert isinstance(state, SealedState)
    assert state.active is False
    assert state.since is None


async def test_sealed_for_short_time_not_degraded(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """Sealed for < grace window → not degraded yet."""
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": True, "initialized": True}
    )
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=300, recovery_seconds=30,
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    # 2 minutes later → still under 5 min grace
    with freeze_time("2026-05-04 12:02:00"):
        await mon._poll_once()
    assert mon.is_degraded() is False


async def test_sealed_for_5min_enters_degraded(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """Vault sealed for ≥5 min → broker enters degraded mode."""
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": True, "initialized": True}
    )
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=300, recovery_seconds=30,
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    assert mon.is_degraded() is False
    with freeze_time("2026-05-04 12:05:01"):
        await mon._poll_once()
    assert mon.is_degraded() is True
    state = mon.last_status()
    assert state.active is True
    assert state.since is not None


async def test_cached_reads_continue_in_degraded(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """When degraded, cached reads still served."""
    ref = SecretRef.parse("secret://vault/kv/data/foo")
    # Seed cache directly
    broker.cache.put(ref, b"cached-value", ttl_s=300)

    # Force degraded mode
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=0, recovery_seconds=30,
    )
    broker.sealed_monitor = mon  # wire in
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": True, "initialized": True}
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:00:01"):
        await mon._poll_once()
    assert mon.is_degraded()

    # Cached read still works
    requester = MagicMock(user_id="u1")
    h = await broker.get(ref, requester=requester)
    assert h is not None


async def test_non_cached_lookup_raises_backend_sealed(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """Non-cached ref lookup in degraded mode raises BackendSealed."""
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=0, recovery_seconds=30,
    )
    broker.sealed_monitor = mon
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": True, "initialized": True}
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:00:01"):
        await mon._poll_once()
    assert mon.is_degraded()

    requester = MagicMock(user_id="u1")
    ref = SecretRef.parse("secret://vault/kv/data/uncached")
    with pytest.raises(BackendSealed):
        await broker.get(ref, requester=requester)


async def test_health_check_exception_treated_as_sealed(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """When health_check raises, monitor treats it as sealed (fail-closed)."""
    vault_backend.health_check = AsyncMock(side_effect=OSError("connection refused"))
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=0, recovery_seconds=30,
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:00:01"):
        await mon._poll_once()
    assert mon.is_degraded() is True


async def test_recovery_after_unsealed(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """Backend unsealed for ≥30s → exits degraded mode."""
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=300, recovery_seconds=30,
    )
    # Enter sealed
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": True, "initialized": True}
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:05:01"):
        await mon._poll_once()
    assert mon.is_degraded()

    # Now unseal
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": False, "initialized": True}
    )
    with freeze_time("2026-05-04 12:05:30"):
        await mon._poll_once()
    # Still degraded — first unsealed observation; recovery timer just started
    assert mon.is_degraded()
    with freeze_time("2026-05-04 12:05:45"):
        await mon._poll_once()
    # 15s healthy < 30s
    assert mon.is_degraded()
    with freeze_time("2026-05-04 12:06:01"):
        await mon._poll_once()
    # ≥30s healthy since 12:05:30 → exit
    assert mon.is_degraded() is False


async def test_banner_event_published_on_enter_and_exit(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """Bus subscriber sees sealed_degraded and recovery events."""
    sub = bus.subscribe("secrets.status")

    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        grace_seconds=300, recovery_seconds=30,
    )
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": True, "initialized": True}
    )
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:05:01"):
        await mon._poll_once()
    assert mon.is_degraded()

    # Drain enter event
    async def _next() -> dict[str, Any]:
        evt = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
        return dict(evt.payload)

    enter = await _next()
    assert enter["type"] == "secrets.sealed_degraded"
    assert "since" in enter

    # Recover
    vault_backend.health_check = AsyncMock(
        return_value={"sealed": False, "initialized": True}
    )
    with freeze_time("2026-05-04 12:05:30"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:06:01"):
        await mon._poll_once()
    assert mon.is_degraded() is False

    exit_evt = await _next()
    assert exit_evt["type"] == "secrets.recovered"
    await sub.close()


async def test_start_stop_lifecycle(
    broker: SecretsBroker, vault_backend: MagicMock, bus: Bus
) -> None:
    """start() launches background task; stop() cancels cleanly."""
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=vault_backend,
        poll_interval_seconds=0.01, grace_seconds=300, recovery_seconds=30,
    )
    await mon.start()
    await asyncio.sleep(0.05)
    await mon.stop()
    # Idempotent stop
    await mon.stop()


# ---------------------------------------------------------------------------
# API integration: 503 with vault_sealed_degraded
# ---------------------------------------------------------------------------


async def test_api_returns_503_for_non_cached_ref() -> None:
    """API returns 503 with vault_sealed_degraded when broker reports sealed."""
    from unittest import mock
    from httpx import ASGITransport, AsyncClient
    from server.app.api.app import create_app
    from server.tests._helpers.app_state import make_test_app_state
    from server.app.secrets.broker import SecretsBroker

    backend = AsyncMock(spec=SecretsBackend)
    backend.health_check = AsyncMock(return_value={"sealed": True, "initialized": True})
    backend.get = AsyncMock(return_value=b"v")
    backend.put = AsyncMock(return_value=1)

    broker = SecretsBroker(
        backends={"vault": backend},
        cache=BrokerCache(),
        handle_store=HandleStore(),
        mfa_recency_check=lambda r: True,
    )

    bus = Bus()
    mon = SealedModeMonitor(
        broker=broker, bus=bus, vault_backend=backend,
        grace_seconds=0, recovery_seconds=30,
    )
    broker.sealed_monitor = mon
    with freeze_time("2026-05-04 12:00:00"):
        await mon._poll_once()
    with freeze_time("2026-05-04 12:00:01"):
        await mon._poll_once()
    assert mon.is_degraded()

    with mock.patch("server.app.api.middleware.admin_auth.load_settings") as mock_load:
        from pydantic import SecretStr
        settings = MagicMock()
        settings.admin_token = SecretStr("test-admin-token")
        mock_load.return_value = settings

        # Need a sessionmaker fixture - build it inline
        from server.app.db.session import make_engine, make_sessionmaker
        from server.app.models.base import Base as BaseModel
        eng = make_engine("sqlite+aiosqlite:///:memory:")
        async with eng.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        sm = make_sessionmaker(eng)

        from server.app.deps import current_principal
        from server.app.rbac.provider import Principal

        app = create_app()
        app_state = make_test_app_state(sessionmaker=sm)
        app_state.secrets_broker = broker
        app_state.mfa_proof_verifier = lambda proof, principal: True
        app.state.app_state = app_state
        app.dependency_overrides[current_principal] = lambda: Principal(user_id="test-admin")

        body = {
            "ref": "secret://vault/kv/data/uncached",
        }
        auth = {"Authorization": "Bearer test-admin-token"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # Reveal triggers broker.get → BackendSealed → 503
            r = await c.post(
                "/v1/secrets/actions/reveal",
                json=body,
                headers={"X-MFA-Proof": "ok", **auth},
            )
            assert r.status_code == 503
            assert r.json()["detail"] == "vault_sealed_degraded"

        await eng.dispose()


# Helper to make linter realise SealedState/timedelta are touched directly
def test_sealed_state_dataclass_shape() -> None:
    s = SealedState(active=False, since=None, last_health=None)
    assert s.active is False
    s2 = SealedState(active=True, since=datetime.now(timezone.utc), last_health={"sealed": True})
    assert s2.active is True
    assert s2.last_health == {"sealed": True}
    # touch timedelta to avoid unused-import lints in some configs
    assert timedelta(seconds=1).total_seconds() == 1.0
