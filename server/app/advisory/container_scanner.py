"""Trivy container scanner bridge — scans OCI images for vulnerabilities."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models.host_container import HostContainer
from server.app.models.host_advisory import HostAdvisory

log = logging.getLogger(__name__)


class TrivyClient:
    """Trivy CLI client for scanning OCI images."""

    def __init__(self, server_url: str = "http://127.0.0.1:8200"):
        """Initialize Trivy client.

        @param server_url Base URL for Trivy server (default: localhost:8200).
        """
        self.server_url = server_url
        self._cache: dict[str, tuple[list[dict], datetime]] = {}
        self._cache_ttl = timedelta(hours=24)

    async def healthcheck(self) -> bool:
        """Check if trivy binary is available.

        @return True if trivy --version succeeds, False otherwise.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "trivy", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            returncode = await proc.wait()
            return returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def scan_image(self, image_ref: str) -> list[dict]:
        """Scan OCI image and return vulnerabilities.

        Results are cached for 24h. Returns empty list on error.

        @param image_ref OCI image reference (e.g., "docker.io/library/nginx:latest").
        @return List of {vuln_id, severity, package, installed_version, fixed_version, cvss}.
        """
        # Check cache
        now = datetime.now(timezone.utc)
        if image_ref in self._cache:
            cached_result, cached_at = self._cache[image_ref]
            if now - cached_at < self._cache_ttl:
                return cached_result

        # Run trivy scan
        try:
            proc = await asyncio.create_subprocess_exec(
                "trivy", "image", "--server", self.server_url, "--format", "json", image_ref,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                log.warning("trivy_scan_failed", image=image_ref, stderr=stderr.decode())
                return []

            # Parse JSON response
            data = json.loads(stdout.decode())
            results = []

            # Extract vulnerabilities from Trivy JSON structure
            for result in data.get("Results", []):
                for vuln in result.get("Vulnerabilities", []):
                    v = {
                        "vuln_id": vuln.get("VulnerabilityID", ""),
                        "severity": vuln.get("Severity", "UNKNOWN"),
                        "package": vuln.get("PkgName", ""),
                        "installed_version": vuln.get("InstalledVersion", ""),
                        "fixed_version": vuln.get("FixedVersion"),
                        "cvss": vuln.get("CVSS", {}).get("ghsa", {}).get("V3Score"),
                    }
                    results.append(v)

            # Cache result
            self._cache[image_ref] = (results, now)
            return results

        except json.JSONDecodeError:
            log.warning("trivy_json_parse_failed", image=image_ref)
            return []
        except Exception as e:
            log.warning("trivy_scan_error", image=image_ref, error=str(e))
            return []


async def scan_host_containers(
    sm: async_sessionmaker[AsyncSession],
    host_id: str,
    *,
    client: TrivyClient | None = None,
) -> int:
    """Scan all containers on a host and upsert HostAdvisory rows.

    Returns count of new/updated HostAdvisory rows.

    @param sm       Async sessionmaker for database access.
    @param host_id  Host ID to scan.
    @param client   Optional TrivyClient (created if not provided).
    @return Count of new/updated HostAdvisory rows.
    """
    # Check if trivy is available
    if shutil.which("trivy") is None:
        log.info("trivy_unavailable", host=host_id)
        return 0

    if client is None:
        client = TrivyClient()

    count = 0
    now = datetime.now(timezone.utc)

    async with sm() as session:
        # Load all HostContainer rows for this host
        stmt = select(HostContainer).where(HostContainer.host_id == host_id)
        containers = (await session.execute(stmt)).scalars().all()

        for container in containers:
            # Scan image
            vulns = await client.scan_image(container.image_ref)

            for vuln in vulns:
                # Create package identifier: image_digest:package_name
                pkg_id = f"{container.image_digest}:{vuln['package']}"

                # Try to find existing HostAdvisory
                stmt_existing = select(HostAdvisory).where(
                    HostAdvisory.host_id == host_id,
                    HostAdvisory.package == pkg_id,
                )
                existing = (await session.execute(stmt_existing)).scalar_one_or_none()

                if existing is None:
                    # Insert new
                    ha = HostAdvisory(
                        host_id=host_id,
                        advisory_id=vuln["vuln_id"],
                        package=pkg_id,
                        ecosystem="OCI",
                        current_version=vuln["installed_version"],
                        fixed_version=vuln["fixed_version"],
                        status="open",
                    )
                    session.add(ha)
                    count += 1
                else:
                    # Update
                    existing.current_version = vuln["installed_version"]
                    existing.fixed_version = vuln["fixed_version"]
                    existing.last_seen = now
                    # TODO: update status if fixed
                    count += 1

        await session.commit()

    return count
