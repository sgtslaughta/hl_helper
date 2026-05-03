from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource
from .scope import SettingScope

# Fields that should be treated as secrets and redacted in effective_config.
SECRET_FIELDS: frozenset[str] = frozenset({
    "vault_token",
    "session_signing_key_ref",  # may carry inline key material in future
    "admin_token",
})

# Per-key scope registry. Anything not listed defaults to RUNTIME_MUTABLE.
SETTING_SCOPES: dict[str, SettingScope] = {
    "data_dir": SettingScope.BOOT_ONLY,
    "db_url": SettingScope.BOOT_ONLY,
    "public_url": SettingScope.RUNTIME_MUTABLE,
    "log_level": SettingScope.RUNTIME_MUTABLE,
    "tz": SettingScope.RUNTIME_MUTABLE,
    "metrics_enabled": SettingScope.RUNTIME_MUTABLE,
    "otel_endpoint": SettingScope.RUNTIME_MUTABLE,
    "trace_sample_rate": SettingScope.RUNTIME_MUTABLE,
    "audit_retention_days": SettingScope.RUNTIME_MUTABLE,
    "vault_addr": SettingScope.BOOT_ONLY,
    "vault_token": SettingScope.BOOT_ONLY,
    "session_signing_key_ref": SettingScope.BOOT_ONLY,
    "admin_token": SettingScope.BOOT_ONLY,
    "bootstrap_admin_email": SettingScope.BOOT_ONLY,
    "idempotency_max_body_bytes": SettingScope.RUNTIME_MUTABLE,
    "rate_limit_max_buckets": SettingScope.RUNTIME_MUTABLE,
    "trusted_proxy_ips": SettingScope.RUNTIME_MUTABLE,
}


class FleetSettings(BaseSettings):
    """Top-level server settings.

    Sources (highest first):
      1. Environment vars (prefix FLEET_)
      2. YAML config file at FLEET_CONFIG_FILE or /data/fleet.yml
      3. Compiled defaults
    """

    model_config = SettingsConfigDict(
        env_prefix="FLEET_",
        env_file=None,  # not using .env
        case_sensitive=False,
        extra="ignore",
    )

    # Boot-only
    data_dir: Path = Field(default=Path("/data"))
    db_url: str = Field(default="sqlite+aiosqlite:////data/fleet.db")

    # Runtime-mutable
    public_url: str = Field(default="https://localhost:8443")
    log_level: str = Field(default="info")
    tz: str = Field(default="UTC")
    metrics_enabled: bool = Field(default=False)
    otel_endpoint: str | None = Field(default=None)
    trace_sample_rate: float = Field(default=0.01)
    audit_retention_days: int = Field(default=0)  # 0 = forever

    # Vault (boot-only when configured)
    vault_addr: str | None = Field(default=None)
    vault_token: SecretStr | None = Field(default=None)

    # Signing key reference
    session_signing_key_ref: str = Field(default="local:/data/keys/session")

    # Admin API token (boot-only)
    admin_token: SecretStr | None = Field(default=None)

    # Bootstrap admin email (boot-only, used by migration)
    bootstrap_admin_email: str | None = Field(default=None)

    # Idempotency middleware settings
    idempotency_max_body_bytes: int = Field(default=1_048_576)  # 1 MiB

    # Rate limiter settings
    rate_limit_max_buckets: int = Field(default=100_000)
    trusted_proxy_ips: list[str] = Field(default_factory=list)

    # Origin tracking — populated by load_settings()
    # key -> "env" | "file" | "default"
    sources_: dict[str, str] = Field(default_factory=dict, exclude=True)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings)  # file source injected explicitly in load_settings()


def scope_for(key: str) -> SettingScope:
    """Get scope for a setting key. Defaults to RUNTIME_MUTABLE."""
    return SETTING_SCOPES.get(key, SettingScope.RUNTIME_MUTABLE)


def load_settings(
    *,
    env: dict[str, str] | None = None,
    config_file: Path | None = None,
) -> FleetSettings:
    """Build FleetSettings from environment + optional YAML file.

    Resolution: env > file > defaults. Tracks origin per key in `.sources_`.
    `env=None` means use os.environ.
    `config_file=None` means look at env var FLEET_CONFIG_FILE; if also unset, no file layer.
    """
    if env is None:
        env = dict(os.environ)

    # Determine config file path
    actual_config_file = config_file
    if actual_config_file is None and "FLEET_CONFIG_FILE" in env:
        actual_config_file = Path(env["FLEET_CONFIG_FILE"])

    # Load YAML file if it exists
    file_data: dict[str, Any] = {}
    if actual_config_file is not None and actual_config_file.exists():
        try:
            content = actual_config_file.read_text()
            file_data = yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {actual_config_file}: {e}")

    # Build merged dict: env values override file values override defaults
    # Convert env dict to uppercase-key form for matching field names
    env_keys_lower = {k.lower(): v for k, v in env.items() if k.startswith("FLEET_")}

    merged = {}
    # Start with file data
    merged.update(file_data)

    # Override with env values (strip FLEET_ prefix)
    for k, v in env_keys_lower.items():
        if k.startswith("fleet_"):
            field_name = k[6:]  # Remove "fleet_" prefix
            merged[field_name] = v

    # Create settings instance with merged data
    s = FleetSettings(**merged)

    # Track origins for each field
    sources_dict: dict[str, str] = {}
    for field_name in FleetSettings.model_fields.keys():
        field_name_lower = field_name.lower()
        env_key = f"fleet_{field_name_lower}"

        if env_key in env_keys_lower:
            sources_dict[field_name] = "env"
        elif field_name in file_data:
            sources_dict[field_name] = "file"
        else:
            sources_dict[field_name] = "default"

    s.sources_ = sources_dict
    return s


def effective_config(s: FleetSettings, *, redact_secrets: bool = True) -> dict[str, Any]:
    """Return current effective config as dict; redacts fields when redact_secrets=True.
    Redaction applies to:
      - Fields whose name is in SECRET_FIELDS, OR
      - Fields whose value is a SecretStr instance
    Includes per-key 'source' from s.sources_.
    Output shape: {key: {"value": ..., "source": ..., "scope": ...}}.
    """
    result = {}
    for field_name, field_info in FleetSettings.model_fields.items():
        value = getattr(s, field_name)

        # Check if field should be redacted: in SECRET_FIELDS or is SecretStr
        should_redact = redact_secrets and (
            field_name in SECRET_FIELDS or isinstance(value, SecretStr)
        )

        if isinstance(value, SecretStr):
            if should_redact:
                displayed_value = "***"
            else:
                displayed_value = value.get_secret_value()
        elif should_redact:
            displayed_value = "***"
        else:
            displayed_value = value

        result[field_name] = {
            "value": displayed_value,
            "source": s.sources_.get(field_name, "unknown"),
            "scope": scope_for(field_name).value,
        }

    return result
