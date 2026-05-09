"""OSV (Open Source Vulnerabilities) feed source."""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import httpx

from server.app.advisory.feeds import AdvisoryFeedSource, FeedAdvisory, FeedAffected

logger = logging.getLogger(__name__)


def parse_osv_record(d: dict) -> FeedAdvisory | None:
    """Parse a single OSV record into FeedAdvisory.

    Skips records without an 'affected' array.
    Maps OSV severity to string ("critical"|"high"|...|"unknown").
    """
    if "affected" not in d or not d["affected"]:
        return None

    affected_list = []
    for aff in d["affected"]:
        pkg_info = aff.get("package", {})
        ecosystem = pkg_info.get("ecosystem", "unknown")
        package = pkg_info.get("name", "")

        if not package:
            continue

        introduced = None
        fixed = None
        range_kind = "ECOSYSTEM"

        for rng in aff.get("ranges", []):
            range_kind = rng.get("type", "ECOSYSTEM")
            for event in rng.get("events", []):
                if "introduced" in event:
                    introduced = event["introduced"]
                if "fixed" in event:
                    fixed = event["fixed"]
                if "last_affected" in event and not fixed:
                    # Distro feeds sometimes use ``last_affected`` for the
                    # final vulnerable version when no fix has shipped.
                    introduced = introduced or event["last_affected"]

        # Some OSV records (notably Ubuntu/Debian) omit ``ranges`` and use a
        # ``versions`` list instead. Surface the first/last so the UI can
        # show *something* rather than empty fields.
        versions = aff.get("versions") or []
        if isinstance(versions, list) and versions and not introduced and not fixed:
            try:
                introduced = str(versions[0])
                if len(versions) > 1:
                    fixed = None  # stays None: no fix recorded
                range_kind = range_kind or "VERSIONS"
            except Exception:
                pass

        affected_list.append(
            FeedAffected(
                ecosystem=ecosystem,
                package=package,
                introduced=introduced,
                fixed=fixed,
                range_kind=range_kind,
            )
        )

    if not affected_list:
        return None

    # Parse severity
    severity = "unknown"
    cvss_v3 = None
    cvss_v4 = None

    distro_text_sev: str | None = None
    for sev in d.get("severity", []):
        sev_type = sev.get("type", "")
        score = sev.get("score")
        if sev_type == "CVSS_V3" and score:
            cvss_v3 = str(score)
        elif sev_type == "CVSS_V4" and score:
            cvss_v4 = str(score)
        elif sev_type in ("Ubuntu", "Debian", "RedHat", "Alpine") and isinstance(score, str):
            # Distro feeds publish textual severity here.
            distro_text_sev = score.strip().lower()

    # Pick severity: explicit distro text > database_specific.severity > derived from CVSS.
    db_specific = d.get("database_specific") or {}
    raw_sev = (
        distro_text_sev
        or (db_specific.get("severity") or "").strip().lower()
    )
    if raw_sev in {"critical", "high", "medium", "moderate", "low", "negligible"}:
        severity = {"moderate": "medium", "negligible": "low"}.get(raw_sev, raw_sev)
    elif cvss_v3:
        try:
            score = float(str(cvss_v3).split("/")[0])
            if score >= 9.0:
                severity = "critical"
            elif score >= 7.0:
                severity = "high"
            elif score >= 4.0:
                severity = "medium"
            elif score > 0:
                severity = "low"
        except (ValueError, IndexError):
            pass

    # Parse published/modified dates
    published = None
    modified = None

    if "published" in d and d["published"]:
        try:
            published = datetime.fromisoformat(d["published"].replace("Z", "+00:00"))
        except Exception:
            pass

    if "modified" in d and d["modified"]:
        try:
            modified = datetime.fromisoformat(d["modified"].replace("Z", "+00:00"))
        except Exception:
            pass

    # Aliases
    aliases = d.get("aliases", [])

    # References
    refs = []
    for ref in d.get("references", []):
        if "url" in ref:
            refs.append(ref["url"])

    # Many distro OSV records leave `summary` empty and put the prose in
    # `details`. Fall back to the first non-blank line of `details`, capped
    # so the API/UI doesn't pull a multi-page markdown blob into a tooltip.
    summary = (d.get("summary") or "").strip()
    if not summary:
        details_text = (d.get("details") or "").strip()
        if details_text:
            for line in details_text.splitlines():
                line = line.strip().lstrip("# ").strip()
                if line:
                    summary = line[:500]
                    break

    return FeedAdvisory(
        id=d.get("id", ""),
        aliases=aliases,
        summary=summary,
        description_md=d.get("description") or d.get("details"),
        severity=severity,
        cvss_v3=cvss_v3,
        cvss_v4=cvss_v4,
        published=published,
        modified=modified,
        refs=refs,
        affected=affected_list,
    )


async def download_zip(url: str, path: Path) -> None:
    """Download a zip file from URL to path."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)


class OSVFeedSource(AdvisoryFeedSource):
    """Sync advisories from OSV."""

    name = "osv"

    async def sync(self) -> list[FeedAdvisory]:
        """Download and parse all OSV records from all.zip."""
        url = "https://osv-vulnerabilities.storage.googleapis.com/all.zip"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "all.zip"
            await download_zip(url, tmp_path)

            advisories = []
            with zipfile.ZipFile(tmp_path, "r") as zf:
                for file_info in zf.filelist:
                    if file_info.filename.endswith(".json"):
                        content = zf.read(file_info.filename)
                        try:
                            record = json.loads(content)
                            adv = parse_osv_record(record)
                            if adv:
                                advisories.append(adv)
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse OSV record {file_info.filename}: {e}"
                            )

            return advisories
