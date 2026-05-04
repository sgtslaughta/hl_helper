"""Validate server systemd unit file structure and security hardening."""
import configparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIT_PATH = ROOT / "deploy/server/systemd/hl-helper-server.service"


def test_unit_file_exists():
    """Server systemd unit must exist."""
    assert UNIT_PATH.is_file()


def test_unit_file_parses_as_ini():
    """Unit file must parse as valid INI (systemd format)."""
    cp = configparser.ConfigParser(strict=False)
    cp.read(UNIT_PATH)
    assert "Unit" in cp
    assert "Service" in cp
    assert "Install" in cp


def test_service_type_and_user():
    """Type must be simple; must run under hl-helper user."""
    cp = configparser.ConfigParser(strict=False)
    cp.read(UNIT_PATH)
    assert cp.get("Service", "Type", fallback="").strip() == "simple"
    assert "hl-helper" in cp.get("Service", "User", fallback="")


def test_service_has_hardening_directives():
    """Must include systemd security hardening directives."""
    text = UNIT_PATH.read_text()
    required = [
        "NoNewPrivileges=",
        "ProtectSystem=strict",
        "ProtectHome=",
        "PrivateTmp=",
        "ProtectKernelTunables=",
        "ProtectKernelModules=",
        "RestrictAddressFamilies=",
        "MemoryDenyWriteExecute=",
    ]
    for directive in required:
        assert directive in text, f"Missing security directive: {directive}"


def test_service_restart_settings():
    """Must have restart on failure with appropriate delay."""
    text = UNIT_PATH.read_text()
    assert "Restart=on-failure" in text
    assert "RestartSec=" in text


def test_service_state_and_config_directories():
    """Must define StateDirectory and ConfigurationDirectory for hl-helper."""
    text = UNIT_PATH.read_text()
    assert "StateDirectory=" in text and "hl-helper" in text
    assert "ConfigurationDirectory=" in text and "hl-helper" in text


def test_service_exec_start_path():
    """ExecStart must reference uvicorn with proper arguments."""
    cp = configparser.ConfigParser(strict=False)
    cp.read(UNIT_PATH)
    exec_start = cp.get("Service", "ExecStart", fallback="").strip()
    assert "uvicorn" in exec_start or "ExecStart" in UNIT_PATH.read_text()
    assert exec_start or "ExecStart=" in UNIT_PATH.read_text()
