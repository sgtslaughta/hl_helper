"""derive_exposure: pure function — scan + host_packages + advisories -> per-advisory tier."""
from __future__ import annotations

from typing import Any

from server.app.posture.exposure.loopback import is_loopback


class Tier:
    NETWORK_EXPOSED = "NETWORK_EXPOSED"
    ACTIVE = "ACTIVE"
    INSTALLED_ONLY = "INSTALLED_ONLY"
    UNKNOWN = "UNKNOWN"


_TIER_RANK = {
    Tier.UNKNOWN: 0,
    Tier.INSTALLED_ONLY: 1,
    Tier.ACTIVE: 2,
    Tier.NETWORK_EXPOSED: 3,
}


def _max_tier(a: str, b: str) -> str:
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


def derive_exposure(
    scan: dict[str, Any],
    host_packages: list[dict[str, Any]],
    advisories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute per-advisory exposure tier + evidence for one host scan.

    Args:
        scan: Dict-shaped RuntimeExposure (proto MessageToDict output OK).
            Keys: processes, listeners, connections, services, kernel_modules,
            container_exposure.
        host_packages: List of {name, version} dicts of installed packages.
        advisories: List of {id, package, affected_paths} dicts. `affected_paths`
            is a list of canonical paths (e.g. `/usr/lib/.../libssl.so.3`).

    Returns:
        List of {advisory_id, exposure_tier, evidence: list[str]} dicts.
        Only advisories whose package is installed on host are returned.
    """
    installed = {p["name"] for p in host_packages}

    # Index processes by pid for listener correlation.
    procs = scan.get("processes") or []
    pid_index = {p["pid"]: p for p in procs}

    out: list[dict[str, Any]] = []
    for adv in advisories:
        pkg = adv["package"]
        if pkg not in installed:
            continue
        affected_paths = set(adv.get("affected_paths") or [])

        tier = Tier.INSTALLED_ONLY
        evidence: list[str] = []

        # 1. Loaded-lib match
        for p in procs:
            libs = p.get("loaded_libs") or []
            hits = [lib for lib in libs if lib in affected_paths]
            if hits:
                tier = _max_tier(tier, Tier.ACTIVE)
                evidence.append(f"loaded by {p['exe_path']} pid {p['pid']}")

        # 2. Process exe match
        for p in procs:
            if p.get("pkg") == pkg:
                tier = _max_tier(tier, Tier.ACTIVE)
                evidence.append(f"running pid {p['pid']} ({p['exe_path']})")

        # 3. Service match
        for s in scan.get("services") or []:
            if s.get("pkg") == pkg and s.get("active"):
                tier = _max_tier(tier, Tier.ACTIVE)
                evidence.append(f"service {s['name']} active")

        # 4. Kernel module match
        for km in scan.get("kernel_modules") or []:
            if km.get("pkg") == pkg:
                tier = _max_tier(tier, Tier.ACTIVE)
                evidence.append(f"kmod {km['name']} loaded")

        # 5. Listener match — promotes to NETWORK_EXPOSED if non-loopback
        for sock in scan.get("listeners") or []:
            sock_pid = sock.get("pid", 0)
            proc = pid_index.get(sock_pid)
            if not proc:
                continue
            proc_libs = set(proc.get("loaded_libs") or [])
            matches = proc.get("pkg") == pkg or bool(proc_libs & affected_paths)
            if not matches:
                continue
            bind_addr = sock.get("bind_addr", "")
            port = sock.get("port", 0)
            proto = sock.get("proto", "tcp")
            if is_loopback(bind_addr):
                tier = _max_tier(tier, Tier.ACTIVE)
                evidence.append(f"listening {proto}/{port} (loopback)")
            else:
                tier = _max_tier(tier, Tier.NETWORK_EXPOSED)
                evidence.append(f"listening {proto}/{port} ({proc['exe_path']})")

        # 6. Container exposure mirrors above per-container — minimal v1: skip,
        # add in follow-up when proto stable. (Keep API surface; tests don't
        # exercise containers yet.)

        out.append(
            {
                "advisory_id": adv["id"],
                "exposure_tier": tier,
                "evidence": evidence,
            }
        )

    return out
