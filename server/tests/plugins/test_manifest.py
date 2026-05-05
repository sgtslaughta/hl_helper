"""Tests for plugin manifest schema and parsing."""

from __future__ import annotations

import pytest

from server.app.plugins.manifest import (
    ALLOWED_CAPABILITIES,
    ManifestError,
    parse_manifest,
    parse_manifest_yaml,
)


class TestPluginManifestValid:
    """Valid manifest acceptance tests."""

    def test_minimal_manifest(self) -> None:
        """Minimal valid manifest is accepted."""
        data = {
            "id": "com.example.plugin",
            "version": "1.0.0",
            "name": "Example Plugin",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {
                "cpu_milli": 100,
                "memory_mib": 128,
                "disk_mib": 0,
            },
        }
        manifest = parse_manifest(data)
        assert manifest.id == "com.example.plugin"
        assert manifest.version == "1.0.0"

    def test_full_manifest(self) -> None:
        """Manifest with all optional fields."""
        data = {
            "id": "io.hl-helper.notify-discord",
            "version": "2.1.0",
            "name": "Discord Notifications",
            "description": "Route alerts to Discord",
            "runtime": "python",
            "capabilities": ["egress.http", "hooks.notification.route"],
            "min_hl_helper_version": "1.0.0",
            "resources": {
                "cpu_milli": 500,
                "memory_mib": 512,
                "disk_mib": 100,
            },
        }
        manifest = parse_manifest(data)
        assert manifest.name == "Discord Notifications"
        assert manifest.description == "Route alerts to Discord"
        assert len(manifest.capabilities) == 2

    def test_valid_runtimes(self) -> None:
        """All valid runtimes are accepted."""
        for runtime in ["binary", "python", "node", "jvm", "wasm"]:
            data = {
                "id": "com.example.test",
                "version": "1.0.0",
                "name": "Test",
                "runtime": runtime,
                "capabilities": [],
                "min_hl_helper_version": "1.0.0",
                "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
            }
            manifest = parse_manifest(data)
            assert manifest.runtime == runtime

    def test_all_allowed_capabilities(self) -> None:
        """All allowed capabilities are accepted."""
        caps = list(ALLOWED_CAPABILITIES)
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": caps,
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
        }
        manifest = parse_manifest(data)
        assert set(manifest.capabilities) == set(caps)

    def test_resource_bounds_min(self) -> None:
        """Minimum resource bounds are accepted."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {
                "cpu_milli": 1,
                "memory_mib": 1,
                "disk_mib": 0,
            },
        }
        manifest = parse_manifest(data)
        assert manifest.resources.cpu_milli == 1
        assert manifest.resources.memory_mib == 1

    def test_resource_bounds_max(self) -> None:
        """Maximum resource bounds are accepted."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {
                "cpu_milli": 8000,
                "memory_mib": 8192,
                "disk_mib": 10240,
            },
        }
        manifest = parse_manifest(data)
        assert manifest.resources.cpu_milli == 8000
        assert manifest.resources.memory_mib == 8192
        assert manifest.resources.disk_mib == 10240


class TestPluginManifestInvalid:
    """Invalid manifest rejection tests."""

    def test_invalid_id_format(self) -> None:
        """Non-reverse-DNS IDs are rejected."""
        for bad_id in ["notadomain", "localhost", "com", "example..test"]:
            data = {
                "id": bad_id,
                "version": "1.0.0",
                "name": "Test",
                "runtime": "binary",
                "capabilities": [],
                "min_hl_helper_version": "1.0.0",
                "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
            }
            with pytest.raises(ManifestError):
                parse_manifest(data)

    def test_id_starting_with_uppercase(self) -> None:
        """IDs must start with lowercase."""
        data = {
            "id": "Com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_invalid_version_format(self) -> None:
        """Non-semver versions are rejected."""
        for bad_version in ["1", "1.0", "latest", "v1.0.0"]:
            data = {
                "id": "com.example.test",
                "version": bad_version,
                "name": "Test",
                "runtime": "binary",
                "capabilities": [],
                "min_hl_helper_version": "1.0.0",
                "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
            }
            with pytest.raises(ManifestError):
                parse_manifest(data)

    def test_invalid_runtime(self) -> None:
        """Invalid runtime values are rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "docker",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_invalid_capability(self) -> None:
        """Disallowed capabilities are rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": ["egress.http", "admin.access"],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_cpu_below_minimum(self) -> None:
        """CPU below 1 milli is rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 0, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_cpu_above_maximum(self) -> None:
        """CPU above 8000 milli is rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 8001, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_memory_below_minimum(self) -> None:
        """Memory below 1 MiB is rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 0, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_memory_above_maximum(self) -> None:
        """Memory above 8192 MiB is rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 8193, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_disk_below_minimum(self) -> None:
        """Disk below 0 MiB is rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": -1},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_disk_above_maximum(self) -> None:
        """Disk above 10240 MiB is rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "Test",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 10241},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_name_too_long(self) -> None:
        """Names over 100 chars are rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "name": "x" * 101,
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)

    def test_missing_required_field(self) -> None:
        """Missing required fields are rejected."""
        data = {
            "id": "com.example.test",
            "version": "1.0.0",
            "runtime": "binary",
            "capabilities": [],
            "min_hl_helper_version": "1.0.0",
            "resources": {"cpu_milli": 100, "memory_mib": 128, "disk_mib": 0},
        }
        with pytest.raises(ManifestError):
            parse_manifest(data)


class TestManifestYamlParsing:
    """YAML parsing tests."""

    def test_parse_manifest_yaml(self) -> None:
        """YAML manifest is parsed correctly."""
        yaml_text = """
id: com.example.plugin
version: 1.0.0
name: Example Plugin
runtime: binary
capabilities: []
min_hl_helper_version: "1.0.0"
resources:
  cpu_milli: 100
  memory_mib: 128
  disk_mib: 0
"""
        manifest = parse_manifest_yaml(yaml_text)
        assert manifest.id == "com.example.plugin"
        assert manifest.version == "1.0.0"

    def test_parse_manifest_yaml_with_capabilities(self) -> None:
        """YAML with capabilities is parsed."""
        yaml_text = """
id: io.hl-helper.notify-discord
version: 2.1.0
name: Discord Notifications
description: Send alerts to Discord
runtime: python
capabilities:
  - egress.http
  - hooks.notification.route
min_hl_helper_version: "1.0.0"
resources:
  cpu_milli: 500
  memory_mib: 512
  disk_mib: 100
"""
        manifest = parse_manifest_yaml(yaml_text)
        assert manifest.id == "io.hl-helper.notify-discord"
        assert set(manifest.capabilities) == {"egress.http", "hooks.notification.route"}

    def test_parse_manifest_yaml_invalid_raises_manifest_error(self) -> None:
        """Invalid YAML manifest raises ManifestError."""
        yaml_text = """
id: badid
version: 1.0.0
name: Test
runtime: binary
capabilities: []
min_hl_helper_version: "1.0.0"
resources:
  cpu_milli: 100
  memory_mib: 128
  disk_mib: 0
"""
        with pytest.raises(ManifestError):
            parse_manifest_yaml(yaml_text)
