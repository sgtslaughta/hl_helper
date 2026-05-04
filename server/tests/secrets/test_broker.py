"""Tests for secrets broker dispatcher and handle store."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.app.secrets.broker import SecretsBroker, ReAuthRequired
from server.app.secrets.handle import SecretHandle, HandleStore
from server.app.secrets.cache import BrokerCache
from server.app.secrets.ref import SecretRef
from server.app.secrets.backends.base import SecretsBackend


@pytest.fixture
def mock_local_backend() -> MagicMock:
    """Create a mock local backend."""
    backend = AsyncMock(spec=SecretsBackend)
    backend.get = AsyncMock(return_value=b"local-secret-value")
    backend.put = AsyncMock(return_value=1)
    backend.versions = AsyncMock(return_value=[1])
    backend.delete = AsyncMock()
    return backend


@pytest.fixture
def mock_vault_backend() -> MagicMock:
    """Create a mock vault backend."""
    backend = AsyncMock(spec=SecretsBackend)
    backend.get = AsyncMock(return_value=b"vault-secret-value")
    backend.put = AsyncMock(return_value=1)
    backend.versions = AsyncMock(return_value=[1])
    backend.delete = AsyncMock()
    return backend


@pytest.fixture
def handle_store() -> HandleStore:
    """Create a fresh handle store."""
    return HandleStore()


@pytest.fixture
def cache() -> BrokerCache:
    """Create a fresh broker cache."""
    return BrokerCache(ttl_seconds=30)


@pytest.fixture
def broker(mock_local_backend: Any, mock_vault_backend: Any, handle_store: HandleStore, cache: BrokerCache) -> SecretsBroker:
    """Create a broker with mocked backends."""
    backends = {
        "local": mock_local_backend,
        "vault": mock_vault_backend,
    }
    return SecretsBroker(
        backends=backends,
        cache=cache,
        handle_store=handle_store,
        audit_chain=None,
        mfa_recency_check=None,
    )


@pytest.mark.asyncio
async def test_get_returns_handle_not_plaintext(broker: SecretsBroker) -> None:
    """Get returns SecretHandle, not plaintext bytes."""
    admin = MagicMock(user_id="admin-user")
    ref = SecretRef.parse("secret://local/foo")
    h = await broker.get(ref, requester=admin)

    assert isinstance(h, SecretHandle)
    assert not hasattr(h, "value")  # no public value attribute


@pytest.mark.asyncio
async def test_reveal_requires_re_auth(broker: SecretsBroker) -> None:
    """Reveal without fresh MFA raises ReAuthRequired."""
    admin = MagicMock(user_id="admin-user")
    ref = SecretRef.parse("secret://local/foo")
    h = await broker.get(ref, requester=admin)

    # Reveal with mfa_recency_check that returns False
    broker.mfa_recency_check = AsyncMock(return_value=False)
    with pytest.raises(ReAuthRequired):
        await broker.reveal(h, requester=admin)


@pytest.mark.asyncio
async def test_reveal_fails_closed_without_mfa_check(broker: SecretsBroker) -> None:
    """Reveal without mfa_recency_check configured raises ReAuthRequired (fail-closed)."""
    admin = MagicMock(user_id="admin-user")
    ref = SecretRef.parse("secret://local/foo")
    h = await broker.get(ref, requester=admin)

    # Broker has no mfa_recency_check (None) - should raise ReAuthRequired
    assert broker.mfa_recency_check is None
    with pytest.raises(ReAuthRequired, match="MFA recency check not configured"):
        await broker.reveal(h, requester=admin)


@pytest.mark.asyncio
async def test_reveal_with_valid_mfa(broker: SecretsBroker) -> None:
    """Reveal with passing MFA returns plaintext."""
    admin = MagicMock(user_id="admin-user")
    ref = SecretRef.parse("secret://local/foo")

    # Create a broker with mfa_recency_check that returns True
    broker_with_mfa = SecretsBroker(
        backends=broker.backends,
        cache=broker.cache,
        handle_store=broker.handle_store,
        audit_chain=broker.audit_chain,
        mfa_recency_check=AsyncMock(return_value=True),
    )

    h = await broker_with_mfa.get(ref, requester=admin)
    val = await broker_with_mfa.reveal(h, requester=admin)

    assert val == b"local-secret-value"


@pytest.mark.asyncio
async def test_dispatch_routes_to_backend(broker: SecretsBroker) -> None:
    """Put routes to correct backend."""
    admin = MagicMock(user_id="admin-user")
    ref_vault = SecretRef.parse("secret://vault/kv/data/x")

    await broker.put(ref_vault, b"vault-value", admin)

    # Verify vault backend was called
    broker.backends["vault"].put.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit(broker: SecretsBroker) -> None:
    """Cache tracks hits correctly."""
    admin = MagicMock(user_id="admin-user")
    ref = SecretRef.parse("secret://local/foo")

    h1 = await broker.get(ref, requester=admin)
    h2 = await broker.get(ref, requester=admin)

    # Both should be SecretHandle but second should be a cache hit
    assert isinstance(h1, SecretHandle)
    assert isinstance(h2, SecretHandle)
    # Check cache hit counters
    assert broker.cache.hits == 1


@pytest.mark.asyncio
async def test_rotate_invalidates_cache(broker: SecretsBroker) -> None:
    """Rotate invalidates cache for that ref."""
    admin = MagicMock(user_id="admin-user")
    ref = SecretRef.parse("secret://local/foo")

    # Prime the cache
    await broker.get(ref, requester=admin)
    _ = broker.cache.hits

    # Rotate
    await broker.rotate(ref, admin)

    # Cache should be cleared for this ref
    assert broker.cache.hits == 0


@pytest.mark.asyncio
async def test_handle_expires(handle_store: HandleStore) -> None:
    """Handles expire after TTL."""
    ref = SecretRef.parse("secret://local/foo")
    value = b"secret-value"
    requester = MagicMock(user_id="user1")

    # Issue a handle with immediate expiry
    h = handle_store.issue(ref, value, requester, expires_in_s=0.01)

    # Should be retrievable immediately
    retrieved = handle_store.lookup(h, requester)
    assert retrieved == value

    # After expiry
    await asyncio.sleep(0.02)
    assert handle_store.lookup(h, requester) is None


@pytest.mark.asyncio
async def test_handle_requester_mismatch_rejected(handle_store: HandleStore) -> None:
    """Handles reject lookups from different requester."""
    ref = SecretRef.parse("secret://local/foo")
    value = b"secret-value"
    requester1 = MagicMock(user_id="user1")
    requester2 = MagicMock(user_id="user2")

    h = handle_store.issue(ref, value, requester1)

    # Lookup from different requester should fail
    assert handle_store.lookup(h, requester2) is None


@pytest.mark.asyncio
async def test_cache_put_get_ttl(cache: BrokerCache) -> None:
    """Cache respects TTL."""
    ref = SecretRef.parse("secret://local/foo")
    value = b"cached-value"

    cache.put(ref, value, ttl_s=0.05)
    assert cache.get(ref) == value
    assert cache.hits == 1  # First get is a hit (after put)

    # Same ref, should hit again
    assert cache.get(ref) == value
    assert cache.hits == 2

    # After TTL expires
    await asyncio.sleep(0.06)
    assert cache.get(ref) is None
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_cache_invalidate(cache: BrokerCache) -> None:
    """Cache invalidate clears specific ref."""
    ref1 = SecretRef.parse("secret://local/foo")
    ref2 = SecretRef.parse("secret://local/bar")

    cache.put(ref1, b"value1", ttl_s=30)
    cache.put(ref2, b"value2", ttl_s=30)

    cache.invalidate(ref1)

    assert cache.get(ref1) is None
    assert cache.get(ref2) == b"value2"


@pytest.mark.asyncio
async def test_cache_clear(cache: BrokerCache) -> None:
    """Cache clear removes all entries."""
    ref1 = SecretRef.parse("secret://local/foo")
    ref2 = SecretRef.parse("secret://local/bar")

    cache.put(ref1, b"value1", ttl_s=30)
    cache.put(ref2, b"value2", ttl_s=30)

    cache.clear()

    assert cache.get(ref1) is None
    assert cache.get(ref2) is None
