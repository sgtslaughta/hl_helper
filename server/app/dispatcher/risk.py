"""Risk classifier: (payload_kind, target_count) → 'low'|'med'|'high'."""

from __future__ import annotations

from typing import Literal

PayloadKind = Literal[
    "pkg_update",
    "shell_exec",
    "reboot",
    "shutdown",
    "container_update",
    "file_transfer",
    "custom",
]
RiskLevel = Literal["low", "med", "high"]


# Default thresholds:
#   reboot/shutdown: 1 host = med, >1 = high.
#   shell_exec / container_exec: always high (arbitrary code).
#   pkg_update + classes={"security"}: low. Other pkg_update: med.
#   file_transfer: med.
#   custom: high (fail-closed).
def classify(
    payload_kind: str,
    target_count: int,
    *,
    payload_metadata: dict[str, object] | None = None,
) -> RiskLevel:
    """Classify risk level based on payload kind and target count."""
    pm = payload_metadata or {}
    if payload_kind in ("shell_exec", "container_exec"):
        return "high"
    if payload_kind in ("reboot", "shutdown"):
        return "high" if target_count > 1 else "med"
    if payload_kind == "pkg_update":
        classes = pm.get("classes") or []
        if classes == ["security"]:
            return "low"
        return "med"
    if payload_kind == "file_transfer":
        return "med"
    if payload_kind == "container_update":
        return "med" if target_count <= 5 else "high"
    if payload_kind == "custom":
        return "high"
    return "high"  # unknown payload → fail-closed
