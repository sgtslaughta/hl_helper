"""MFA plugin slot — Protocol + module-level registry.

Plugins implement :class:`MfaPluginProtocol` and register themselves with the
module-level :data:`_registry` (or any other :class:`MfaPluginRegistry`
instance). The /v1/mfa/challenge endpoint routes ``method=<plugin_name>``
through the registry when no built-in handler matches.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MfaPluginProtocol(Protocol):
    """Protocol for pluggable MFA factors.

    Attributes:
        name: Stable identifier used as the ``method`` value in API requests.
    """

    name: str

    async def begin(self, user: Any, ctx: dict[str, Any]) -> dict[str, Any]:
        """Initiate an MFA challenge; return opaque per-method context."""
        ...

    async def verify(self, user: Any, proof: dict[str, Any]) -> bool:
        """Verify a proof submitted by the user. Return True on success."""
        ...

    async def list_methods(self) -> list[str]:
        """Return the method names this plugin advertises."""
        ...


class MfaPluginRegistry:
    """In-process registry for MFA plugin instances keyed by name."""

    def __init__(self) -> None:
        self._plugins: dict[str, MfaPluginProtocol] = {}

    def register(self, plugin: MfaPluginProtocol) -> None:
        """Register a plugin under its ``name`` attribute (last write wins)."""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> MfaPluginProtocol | None:
        """Return the registered plugin or ``None`` if unknown."""
        return self._plugins.get(name)

    def methods(self) -> list[str]:
        """Return aggregate method names advertised by all plugins."""
        names: set[str] = set()
        for plugin in self._plugins.values():
            names.add(plugin.name)
        return sorted(names)


# Module-level singleton; import as ``from ... import _registry``.
_registry = MfaPluginRegistry()
