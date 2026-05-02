"""Validate systemd unit file against systemd-analyze and basic schema."""
import configparser
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIT_PATH = ROOT / "deploy/agent/systemd/hl-agent.service"

def test_unit_file_exists():
    assert UNIT_PATH.is_file()

def test_unit_file_parses_as_ini():
    cp = configparser.ConfigParser(strict=False)
    cp.read(UNIT_PATH)
    assert "Unit" in cp
    assert "Service" in cp
    assert "Install" in cp

def test_service_has_hardening_directives():
    text = UNIT_PATH.read_text()
    for directive in [
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "PrivateTmp=true",
        "ReadWritePaths=/var/lib/hl-agent",
        "RestartSec=",
    ]:
        assert directive in text, f"missing: {directive}"

def test_systemd_analyze_security_passes():
    sa = shutil.which("systemd-analyze")
    if sa is None:
        return  # not available in CI runner — skip
    res = subprocess.run([sa, "verify", str(UNIT_PATH)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
