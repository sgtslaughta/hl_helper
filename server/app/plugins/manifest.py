"""Plugin manifest schema and parsing."""

from __future__ import annotations

import re
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

ALLOWED_CAPABILITIES: frozenset[str] = frozenset({
    "egress.http",
    "egress.tcp",
    "secrets.read",
    "hooks.update.pre",
    "hooks.update.post",
    "hooks.task.created",
    "hooks.notification.route",
    "storage.local",
})


class ResourceLimits(BaseModel):
    """Resource limits for plugin execution."""

    cpu_milli: int = Field(ge=1, le=8000, description="CPU in millicores")
    memory_mib: int = Field(ge=1, le=8192, description="Memory in MiB")
    disk_mib: int = Field(ge=0, le=10240, description="Disk in MiB")


class PluginManifest(BaseModel):
    """Plugin manifest schema."""

    id: str = Field(max_length=200, description="Reverse-DNS plugin ID")
    version: str = Field(max_length=50, description="Semantic version")
    name: str = Field(max_length=100, description="Display name")
    runtime: Literal["binary", "python", "node", "jvm", "wasm"]
    capabilities: list[str] = Field(default_factory=list)
    min_hl_helper_version: str = Field(max_length=50)
    resources: ResourceLimits
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        r"""ID must be reverse-DNS: ^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$"""
        if not re.match(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$", v):
            raise ValueError(
                "Plugin ID must be reverse-DNS format: "
                "^[a-z][a-z0-9-]*(\\.[a-z][a-z0-9-]*)+$"
            )
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        r"""Version must be semver: ^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$"""
        if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$", v):
            raise ValueError(
                "Version must be semantic: ^\\d+\\.\\d+\\.\\d+(-[a-zA-Z0-9.-]+)?$"
            )
        return v

    @field_validator("min_hl_helper_version")
    @classmethod
    def validate_min_version(cls, v: str) -> str:
        """Minimum version must be semver."""
        if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$", v):
            raise ValueError(
                "Min version must be semantic: ^\\d+\\.\\d+\\.\\d+(-[a-zA-Z0-9.-]+)?$"
            )
        return v

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: list[str]) -> list[str]:
        """All capabilities must be in ALLOWED_CAPABILITIES."""
        invalid = set(v) - ALLOWED_CAPABILITIES
        if invalid:
            raise ValueError(
                f"Invalid capabilities: {invalid}. "
                f"Allowed: {ALLOWED_CAPABILITIES}"
            )
        return v


class ManifestError(Exception):
    """Raised on manifest parsing or validation failure."""

    pass


def parse_manifest(data: dict[str, Any]) -> PluginManifest:
    """Parse and validate manifest dict.

    Args:
        data: Manifest dict.

    Returns:
        PluginManifest instance.

    Raises:
        ManifestError: On validation failure with structured message.
    """
    try:
        return PluginManifest(**data)
    except Exception as e:
        raise ManifestError(f"Invalid manifest: {e}") from e


def parse_manifest_yaml(text: str) -> PluginManifest:
    """Parse and validate manifest from YAML text.

    Args:
        text: YAML manifest text.

    Returns:
        PluginManifest instance.

    Raises:
        ManifestError: On parsing or validation failure.
    """
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ManifestError("YAML must parse to dict")
        return parse_manifest(data)
    except ManifestError:
        raise
    except Exception as e:
        raise ManifestError(f"Failed to parse YAML: {e}") from e
