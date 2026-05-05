"""Plugin system public API."""

from __future__ import annotations

from server.app.models.plugin import PLUGIN_STATES
from server.app.plugins.manifest import (
    ALLOWED_CAPABILITIES,
    ManifestError,
    PluginManifest,
    parse_manifest,
    parse_manifest_yaml,
)
from server.app.plugins.registry import (
    CapabilityMismatchError,
    InvalidStateError,
    NotAcknowledgedError,
    PluginError,
    PluginNotFoundError,
    PluginRegistry,
)

__all__ = [
    "PluginRegistry",
    "PluginManifest",
    "parse_manifest",
    "parse_manifest_yaml",
    "ManifestError",
    "PluginError",
    "CapabilityMismatchError",
    "NotAcknowledgedError",
    "InvalidStateError",
    "PluginNotFoundError",
    "ALLOWED_CAPABILITIES",
    "PLUGIN_STATES",
]
