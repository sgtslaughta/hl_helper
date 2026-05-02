"""Validate sudoers fragments by structure (visudo not always present)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUDOERS_DIR = ROOT / "deploy/agent/sudoers.d"

DISTROS = ["debian", "rhel", "arch", "alpine"]

def test_sudoers_per_distro_present():
    for d in DISTROS:
        p = SUDOERS_DIR / f"hl-agent-{d}"
        assert p.is_file(), f"missing sudoers fragment for {d}: {p}"

def test_sudoers_have_no_password_directive():
    for d in DISTROS:
        text = (SUDOERS_DIR / f"hl-agent-{d}").read_text()
        assert "NOPASSWD" in text, f"{d} sudoers missing NOPASSWD"

def test_sudoers_user_is_hl_agent():
    for d in DISTROS:
        text = (SUDOERS_DIR / f"hl-agent-{d}").read_text()
        # Each non-comment, non-Defaults line should start with hl-agent
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("Defaults"):
                continue
            assert line.startswith("hl-agent "), f"{d}: line does not target hl-agent user: {line!r}"
