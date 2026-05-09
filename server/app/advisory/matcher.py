"""Advisory matcher — joins host_packages × affected_packages → host_advisories."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models.advisory import AffectedPackage
from server.app.models.host_package import HostPackage
from server.app.models.host_advisory import HostAdvisory
from server.app.models.host import Host


# Ecosystem mapping from agent's package-manager identifier ("dpkg", "rpm", ...)
# to candidate OSV-style ecosystem strings, parameterised by host OS facts.
# OSV publishes per-distro/version feeds, so a single agent ecosystem expands
# to multiple advisory ecosystems we should match against.
_DPKG_VERSION_MAP = {
    "16.04": ["Ubuntu:16.04:LTS", "Ubuntu:Pro:16.04:LTS"],
    "18.04": ["Ubuntu:18.04:LTS", "Ubuntu:Pro:18.04:LTS"],
    "20.04": ["Ubuntu:20.04:LTS", "Ubuntu:Pro:20.04:LTS"],
    "22.04": ["Ubuntu:22.04:LTS", "Ubuntu:Pro:22.04:LTS"],
    "24.04": ["Ubuntu:24.04:LTS", "Ubuntu:Pro:24.04:LTS"],
    "11": ["Debian:11"],
    "12": ["Debian:12"],
    "13": ["Debian:13"],
    "14": ["Debian:14"],
}

_RPM_VERSION_MAP = {
    "8": [
        "Red Hat:enterprise_linux:8::appstream",
        "Red Hat:enterprise_linux:8::baseos",
        "AlmaLinux:8",
        "Rocky Linux:8",
    ],
    "9": [
        "Red Hat:enterprise_linux:9::appstream",
        "Red Hat:enterprise_linux:9::baseos",
        "AlmaLinux:9",
        "Rocky Linux:9",
    ],
}


def _candidate_ecosystems(host_pkg_ecosystem: str, os_version: str | None) -> list[str]:
    """Translate agent's ecosystem + host OS version to OSV ecosystem candidates.

    Returns a list including the raw input so language ecosystems (PyPI, npm,
    cargo, Go, gem) pass through unchanged.
    """
    out: list[str] = [host_pkg_ecosystem]
    if not os_version:
        return out
    short = os_version.split(".")[0] if "." not in os_version[:5] else os_version
    if host_pkg_ecosystem == "dpkg":
        out.extend(_DPKG_VERSION_MAP.get(os_version, _DPKG_VERSION_MAP.get(short, [])))
    elif host_pkg_ecosystem == "rpm":
        out.extend(_RPM_VERSION_MAP.get(short, []))
    return out


def _in_range(
    current: str, introduced: str | None, fixed: str | None, ecosystem: str
) -> bool:
    """Check if current version is in vulnerable range [introduced, fixed).

    @param current      Current installed version.
    @param introduced   First vulnerable version (inclusive), or None.
    @param fixed        First fixed version (exclusive), or None.
    @param ecosystem    Package ecosystem (PyPI, npm, Go, Maven, etc).
    @return True if current is in vulnerable range.
    """
    # Import packaging for standard ecosystems
    try:
        from packaging.version import Version
    except ImportError:
        # Fallback: string comparison (best-effort)
        Version = None

    # Ecosystems that use packaging.version
    if ecosystem in ("PyPI", "Go", "Maven", "NuGet", "crates.io"):
        if Version is None:
            # Fallback to tuple comparison
            return _tuple_compare(current, introduced, fixed)
        try:
            cur = Version(current)
            intro = Version(introduced) if introduced else None
            fix = Version(fixed) if fixed else None
        except Exception:
            # Malformed version, assume not vulnerable
            return False
    elif ecosystem in ("npm", "Debian", "Ubuntu", "RHEL", "Alpine", "Arch"):
        # npm: try packaging.version first, fallback to string
        if ecosystem == "npm" and Version is not None:
            try:
                cur = Version(current)
                intro = Version(introduced) if introduced else None
                fix = Version(fixed) if fixed else None
            except Exception:
                # Fallback to string compare
                return _tuple_compare(current, introduced, fixed)
        else:
            # Debian/Ubuntu/RHEL/Alpine/Arch: string comparison
            # TODO: implement proper distro-specific version comparison
            return _tuple_compare(current, introduced, fixed)
    else:
        # Unknown ecosystem, fallback to string
        return _tuple_compare(current, introduced, fixed)

    # Check range: introduced <= current < fixed
    if intro is not None and cur < intro:
        return False
    if fix is not None and cur >= fix:
        return False
    return True


def _tuple_compare(
    current: str, introduced: str | None, fixed: str | None
) -> bool:
    """Fallback tuple-based version comparison for non-standard ecosystems.

    Splits on dots and compares numerically where possible. Mixes of numeric
    and non-numeric segments (common in distro versions like 1.2-3ubuntu5)
    can't be compared directly — we coerce each segment to (int, str) pair so
    Python's tuple ordering stays well-defined.
    """
    def version_tuple(v: str) -> tuple:
        if not v:
            return ()
        parts = v.replace("-", ".").replace("+", ".").split(".")
        result: list[tuple[int, str]] = []
        for p in parts:
            num = 0
            tail = p
            i = 0
            while i < len(p) and p[i].isdigit():
                i += 1
            if i > 0:
                try:
                    num = int(p[:i])
                    tail = p[i:]
                except ValueError:
                    pass
            result.append((num, tail))
        return tuple(result)

    try:
        cur_tuple = version_tuple(current)
        intro_tuple = version_tuple(introduced) if introduced else None
        fix_tuple = version_tuple(fixed) if fixed else None

        if intro_tuple is not None and cur_tuple < intro_tuple:
            return False
        if fix_tuple is not None and cur_tuple >= fix_tuple:
            return False
        return True
    except TypeError:
        # Last-resort lexicographic fallback if the (int, str) coercion still
        # produced incomparable shapes for this ecosystem.
        if introduced and current < introduced:
            return False
        if fixed and current >= fixed:
            return False
        return True


async def match_host(
    sm: async_sessionmaker[AsyncSession],
    host_id: str,
    *,
    catalog_sm: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    """Match host packages against affected packages and upsert host advisories.

    Translates the agent's package-manager ecosystem (e.g. "dpkg") to the
    set of OSV-style ecosystems for the host's OS version, then queries the
    AffectedPackage table via SQL on (ecosystem, package_name) so we don't
    load all 3M+ rows into memory.

    @param sm           Fleet sessionmaker (Host, HostPackage, HostAdvisory).
    @param host_id      The host to match.
    @param catalog_sm   Catalog sessionmaker (AffectedPackage). Defaults to
                        ``sm`` so existing tests/single-engine deployments
                        keep working.

    @return count of new/updated HostAdvisory rows.
    """
    count = 0
    now = datetime.now(timezone.utc)
    catalog = catalog_sm or sm

    async with sm() as session:
        host = await session.get(Host, host_id)
        if host is None:
            return 0

        survey = host.survey or {}
        os_version = survey.get("os_version") if isinstance(survey, dict) else None

        stmt_hp = select(HostPackage).where(HostPackage.host_id == host_id)
        host_pkgs = list((await session.execute(stmt_hp)).scalars().all())
        if not host_pkgs:
            return 0

        # Group host packages by raw ecosystem so we issue one query per group.
        by_eco: dict[str, list[HostPackage]] = {}
        for hp in host_pkgs:
            by_eco.setdefault(hp.ecosystem, []).append(hp)

        for raw_eco, pkgs in by_eco.items():
            candidates = _candidate_ecosystems(raw_eco, os_version)
            pkg_names = list({p.name for p in pkgs})
            by_name: dict[str, list[HostPackage]] = {}
            for p in pkgs:
                by_name.setdefault(p.name, []).append(p)

            async with catalog() as cat_session:
                stmt_ap = select(AffectedPackage).where(
                    AffectedPackage.ecosystem.in_(candidates),
                    AffectedPackage.package.in_(pkg_names),
                )
                affected_rows = list(
                    (await cat_session.execute(stmt_ap)).scalars().all()
                )

            for ap in affected_rows:
                for host_pkg in by_name.get(ap.package, []):
                    is_vulnerable = _in_range(
                        host_pkg.version, ap.introduced, ap.fixed, ap.ecosystem
                    )
                    new_status = "fixed" if (ap.fixed and not is_vulnerable) else "open"

                    stmt_existing = select(HostAdvisory).where(
                        HostAdvisory.host_id == host_id,
                        HostAdvisory.advisory_id == ap.advisory_id,
                        HostAdvisory.package == ap.package,
                    )
                    existing = (
                        await session.execute(stmt_existing)
                    ).scalar_one_or_none()

                    if existing is None:
                        if not is_vulnerable:
                            continue
                        ha = HostAdvisory(
                            host_id=host_id,
                            advisory_id=ap.advisory_id,
                            package=ap.package,
                            ecosystem=ap.ecosystem,
                            current_version=host_pkg.version,
                            fixed_version=ap.fixed,
                            status=new_status,
                        )
                        session.add(ha)
                        count += 1
                    else:
                        existing.current_version = host_pkg.version
                        existing.fixed_version = ap.fixed
                        existing.last_seen = now
                        existing.status = new_status
                        count += 1

        await session.commit()

    return count


async def match_all_hosts(sm: async_sessionmaker[AsyncSession]) -> int:
    """Convenience loop over all enrolled hosts.

    @param sm Async sessionmaker for database access.
    @return Total count of new/updated HostAdvisory rows across all hosts.
    """
    total = 0

    async with sm() as session:
        stmt = select(Host.id)
        host_ids = (await session.execute(stmt)).scalars().all()

    for host_id in host_ids:
        total += await match_host(sm, host_id)

    return total
