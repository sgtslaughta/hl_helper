"""KEV (Known Exploited Vulnerabilities) feed source."""

from __future__ import annotations

import logging

import httpx

from server.app.advisory.feeds import ScoreFeedSource

logger = logging.getLogger(__name__)


def parse_kev_json(d: dict) -> dict[str, bool]:
    """Parse KEV JSON into cveID -> True dict."""
    scores = {}
    for vuln in d.get("vulnerabilities", []):
        cve_id = vuln.get("cveID")
        if cve_id:
            scores[cve_id] = True
    return scores


class KEVScoreFeed(ScoreFeedSource):
    """Sync KEV list from CISA."""

    name = "kev"

    async def sync(self) -> dict[str, bool]:
        """Download and parse KEV JSON."""
        url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            data = response.json()

        return parse_kev_json(data)
