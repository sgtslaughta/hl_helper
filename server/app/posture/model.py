"""Posture finding dataclass + severity ordering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "high", "medium", "low", "info"]


@dataclass(frozen=True)
class Finding:
    """A single posture finding."""

    id: str
    severity: Severity
    title: str
    summary: str
    fix_action_url: str | None = None
    docs_url: str | None = None


# Severity ordering for sorting (lower = more severe).
SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


__all__ = ["Finding", "Severity", "SEVERITY_ORDER"]
