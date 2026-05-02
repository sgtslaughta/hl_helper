import pytest
from pathlib import Path
from server.app.settings.config import (
    load_settings,
    effective_config,
    scope_for,
)
from server.app.settings.scope import SettingScope


class TestDefaults:
    def test_defaults_when_no_env_no_file(self) -> None:
        """Load defaults with no env, no file."""
        s = load_settings(env={}, config_file=None)
        assert s.data_dir == Path("/data")
        assert s.metrics_enabled is False
        assert s.log_level == "info"
        assert s.sources_["data_dir"] == "default"


class TestEnvironmentOverride:
    def test_env_override(self) -> None:
        """Environment vars override defaults."""
        s = load_settings(
            env={
                "FLEET_LOG_LEVEL": "debug",
                "FLEET_METRICS_ENABLED": "true",
            },
            config_file=None,
        )
        assert s.log_level == "debug"
        assert s.metrics_enabled is True
        assert s.sources_["log_level"] == "env"
        assert s.sources_["metrics_enabled"] == "env"


class TestFileOverride:
    def test_file_override(self, tmp_path: Path) -> None:
        """YAML file overrides defaults."""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            "log_level: warning\naudit_retention_days: 30\n"
        )
        s = load_settings(env={}, config_file=config_file)
        assert s.log_level == "warning"
        assert s.audit_retention_days == 30
        assert s.sources_["log_level"] == "file"
        assert s.sources_["audit_retention_days"] == "file"


class TestPrecedence:
    def test_env_beats_file(self, tmp_path: Path) -> None:
        """Environment vars beat file values."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("log_level: warning\n")
        s = load_settings(
            env={"FLEET_LOG_LEVEL": "error"},
            config_file=config_file,
        )
        assert s.log_level == "error"
        assert s.sources_["log_level"] == "env"


class TestFileHandling:
    def test_missing_file_is_ok(self, tmp_path: Path) -> None:
        """Missing config file does not raise."""
        s = load_settings(env={}, config_file=tmp_path / "nope.yml")
        assert s.log_level == "info"
        assert s.sources_["log_level"] == "default"

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        """Invalid YAML raises an error."""
        config_file = tmp_path / "bad.yml"
        config_file.write_text(": invalid yaml :: ::")
        with pytest.raises(Exception):  # yaml.YAMLError or ValueError
            load_settings(env={}, config_file=config_file)


class TestSecretRedaction:
    def test_secret_redacted_in_effective_config(self) -> None:
        """Secrets are redacted in effective_config by default."""
        s = load_settings(
            env={"FLEET_VAULT_TOKEN": "hunter2"},
            config_file=None,
        )
        config_dict = effective_config(s, redact_secrets=True)
        # vault_token should be redacted
        assert config_dict["vault_token"]["value"] == "***"

    def test_secret_not_redacted_when_disabled(self) -> None:
        """Secrets are visible when redact_secrets=False."""
        s = load_settings(
            env={"FLEET_VAULT_TOKEN": "hunter2"},
            config_file=None,
        )
        config_dict = effective_config(s, redact_secrets=False)
        assert config_dict["vault_token"]["value"] == "hunter2"


class TestEffectiveConfig:
    def test_effective_config_includes_scope(self) -> None:
        """effective_config includes scope for each key."""
        s = load_settings(env={}, config_file=None)
        config_dict = effective_config(s)
        assert config_dict["data_dir"]["scope"] == "boot-only"
        assert config_dict["log_level"]["scope"] == "runtime-mutable"
        assert config_dict["vault_addr"]["scope"] == "boot-only"


class TestScopeFunction:
    def test_scope_for_unknown_key_defaults_runtime(self) -> None:
        """Unknown keys default to RUNTIME_MUTABLE."""
        scope = scope_for("totally_made_up")
        assert scope == SettingScope.RUNTIME_MUTABLE


class TestTypeCoercion:
    def test_bool_coercion_from_env(self) -> None:
        """Boolean values coerce from env strings."""
        s1 = load_settings(
            env={"FLEET_METRICS_ENABLED": "true"},
            config_file=None,
        )
        assert s1.metrics_enabled is True

        s2 = load_settings(
            env={"FLEET_METRICS_ENABLED": "false"},
            config_file=None,
        )
        assert s2.metrics_enabled is False

        s3 = load_settings(
            env={"FLEET_METRICS_ENABLED": "0"},
            config_file=None,
        )
        assert s3.metrics_enabled is False

        s4 = load_settings(
            env={"FLEET_METRICS_ENABLED": "1"},
            config_file=None,
        )
        assert s4.metrics_enabled is True

    def test_path_coercion(self) -> None:
        """Path strings coerce to Path objects."""
        s = load_settings(
            env={"FLEET_DATA_DIR": "/var/lib/fleet"},
            config_file=None,
        )
        assert s.data_dir == Path("/var/lib/fleet")


class TestConfigFileFromEnv:
    def test_config_file_path_from_env(self, tmp_path: Path) -> None:
        """FLEET_CONFIG_FILE env var points to config file."""
        config_file = tmp_path / "cfg.yml"
        config_file.write_text("log_level: debug\n")
        s = load_settings(
            env={"FLEET_CONFIG_FILE": str(config_file)},
            config_file=None,
        )
        assert s.log_level == "debug"
        assert s.sources_["log_level"] == "file"
