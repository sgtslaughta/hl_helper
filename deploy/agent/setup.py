#!/usr/bin/env python3
"""
Post-install setup script for hl-agent deployment files.
Sets executable permissions on build scripts.
Run this after extracting the deployment package.
"""
import os
import sys
from pathlib import Path

def setup():
    """Set executable permissions on build scripts."""
    root = Path(__file__).parent
    scripts = [
        root / "build.sh",
        root / "build_native.sh",
    ]

    for script in scripts:
        if script.exists():
            # Add execute bit
            current_mode = script.stat().st_mode
            new_mode = current_mode | 0o111
            os.chmod(script, new_mode)
            print(f"✓ {script.name}")
        else:
            print(f"✗ {script.name} not found", file=sys.stderr)
            return False

    return True

if __name__ == "__main__":
    success = setup()
    sys.exit(0 if success else 1)
