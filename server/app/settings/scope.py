from __future__ import annotations
from enum import Enum


class SettingScope(str, Enum):
    BOOT_ONLY = "boot-only"  # changes need restart
    RUNTIME_MUTABLE = "runtime-mutable"  # changeable at runtime
    ENV_LOCKED = "env-locked"  # locked when set via env var
