"""Secrets broker: dispatcher routing secrets across backends."""

from __future__ import annotations

import structlog
from typing import Any, Callable, cast

from server.app.secrets.cache import BrokerCache
from server.app.secrets.handle import HandleStore, SecretHandle
from server.app.secrets.ref import SecretRef
from server.app.secrets.backends.base import SecretsBackend

log = structlog.get_logger(__name__)


class ReAuthRequired(Exception):
    """Raised when re-authentication is required to reveal a secret."""

    pass


class SecretsBroker:
    """Dispatcher routing secrets across configured backends.

    Routes on SecretRef.backend to the appropriate backend implementation.
    Returns opaque SecretHandle to callers; requires re-auth via reveal().
    """

    def __init__(
        self,
        backends: dict[str, SecretsBackend],
        cache: BrokerCache,
        handle_store: HandleStore,
        audit_chain: Any = None,
        mfa_recency_check: Callable[[Any], bool] | None = None,
    ) -> None:
        """Initialize broker.

        Args:
            backends: Dict mapping backend name to SecretsBackend instance
            cache: BrokerCache for caching secret values
            handle_store: HandleStore for opaque token management
            audit_chain: Optional audit chain for logging actions
            mfa_recency_check: Optional async callable(requester) -> bool
                Returns True if MFA was performed recently, False otherwise
        """
        self.backends = backends
        self.cache = cache
        self.handle_store = handle_store
        self.audit_chain = audit_chain
        self.mfa_recency_check = mfa_recency_check

    async def get(self, ref: SecretRef, requester: Any) -> SecretHandle:
        """Retrieve secret and return opaque handle.

        Retrieves secret from backend (or cache), stores in handle store,
        returns opaque SecretHandle. Caller must use reveal() to access value.

        Args:
            ref: SecretRef to retrieve
            requester: Requester object with user_id attribute

        Returns:
            SecretHandle (does not contain plaintext value)

        Raises:
            KeyError: If secret not found or backend not found
        """
        # Try cache first
        cached_value = self.cache.get(ref)
        if cached_value is not None:
            handle = self.handle_store.issue(ref, cached_value, requester)
            return handle

        # Miss: fetch from backend
        value = await self._raw_get(ref)

        # Cache for 30 seconds
        self.cache.put(ref, value, ttl_s=30)

        # Issue handle
        handle = self.handle_store.issue(ref, value, requester)
        return handle

    async def _raw_get(self, ref: SecretRef) -> bytes:
        """Internal: fetch secret directly from backend without caching.

        Args:
            ref: SecretRef to retrieve

        Returns:
            Secret value in bytes

        Raises:
            KeyError: If secret not found or backend not found
        """
        if ref.backend not in self.backends:
            raise KeyError(f"Backend not configured: {ref.backend}")

        backend = self.backends[ref.backend]
        path = ref.path
        if ref.field:
            path = f"{path}#{ref.field}"

        value = await backend.get(path)
        return value

    async def reveal(self, handle: SecretHandle, requester: Any) -> bytes:
        """Reveal secret value from handle with re-auth gate.

        Requires mfa_recency_check to be configured and return True.
        Production must opt in by passing a callable during init.

        Logs audit event on success.

        Args:
            handle: SecretHandle to reveal
            requester: Requester object with user_id attribute

        Returns:
            Secret value in bytes

        Raises:
            ReAuthRequired: If mfa_recency_check not configured or returns False
        """
        # Fail-closed: require explicit mfa_recency_check
        if self.mfa_recency_check is None:
            raise ReAuthRequired("MFA recency check not configured")

        result = self.mfa_recency_check(requester)
        # Handle both sync and async returns
        if hasattr(result, "__await__"):
            is_recent = await cast(Any, result)
        else:
            is_recent = result
        if not is_recent:
            raise ReAuthRequired("Fresh MFA required to reveal secret")

        # Look up in handle store
        value = self.handle_store.lookup(handle, requester)
        if value is None:
            raise ValueError("Handle not found or expired")

        # Audit
        if self.audit_chain is not None:
            try:
                # Audit without logging the plaintext!
                await self.audit_chain.append(
                    session=None,
                    actor=requester.user_id,
                    action="secret.revealed",
                    subject=str(handle.ref),
                    payload={"ref": str(handle.ref)},
                )
            except Exception as e:
                log.exception("audit_failed", exc=e)

        return value

    async def put(self, ref: SecretRef, value: bytes, requester: Any) -> int:
        """Store secret value.

        Dispatches to appropriate backend, invalidates cache, logs audit.

        Args:
            ref: SecretRef to store
            value: Secret value in bytes
            requester: Requester object with user_id attribute

        Returns:
            Version number from backend

        Raises:
            ValueError: If backend not found
        """
        if ref.backend not in self.backends:
            raise ValueError(f"Backend not configured: {ref.backend}")

        backend = self.backends[ref.backend]
        path = ref.path
        if ref.field:
            path = f"{path}#{ref.field}"

        version = await backend.put(path, value)

        # Invalidate cache
        self.cache.invalidate(ref)

        # Audit
        if self.audit_chain is not None:
            try:
                await self.audit_chain.append(
                    session=None,
                    actor=requester.user_id,
                    action="secret.put",
                    subject=str(ref),
                    payload={"ref": str(ref), "version": version},
                )
            except Exception as e:
                log.exception("audit_failed", exc=e)

        return version

    async def rotate(self, ref: SecretRef, requester: Any) -> int:
        """Rotate a secret by bumping its backend version.

        Reads current value and writes it back to create a new version,
        then invalidates cache.

        Args:
            ref: SecretRef to rotate
            requester: Requester object with user_id attribute

        Returns:
            New version number from backend

        Raises:
            KeyError: If secret not found
        """
        # Read current value
        value = await self._raw_get(ref)

        # Write back to create new version
        version = await self.put(ref, value, requester)

        # Audit (put already audited, but log rotate explicitly)
        if self.audit_chain is not None:
            try:
                await self.audit_chain.append(
                    session=None,
                    actor=requester.user_id,
                    action="secret.rotated",
                    subject=str(ref),
                    payload={"ref": str(ref), "version": version},
                )
            except Exception as e:
                log.exception("audit_failed", exc=e)

        return version

    async def list_refs(self, backend_name: str | None = None) -> list[SecretRef]:
        """List available secret refs (best-effort).

        Attempts to enumerate refs via backend.enumerate_paths() where available.
        Returns distinct paths as SecretRef objects. Returns empty list if backend
        does not support enumeration.

        Args:
            backend_name: Optional backend to list from; defaults to all

        Returns:
            List of SecretRef objects
        """
        refs: list[SecretRef] = []

        backends_to_list = (
            {backend_name: self.backends[backend_name]}
            if backend_name
            else self.backends
        )

        for name, backend in backends_to_list.items():
            # Best-effort enumeration - not all backends support it
            if hasattr(backend, "enumerate_paths"):
                try:
                    paths = await backend.enumerate_paths()
                    for path in paths:
                        refs.append(SecretRef(backend=name, path=path, field=None))
                except Exception as e:
                    log.warning("enumerate_paths failed for backend %s: %s", name, e)

        return refs
