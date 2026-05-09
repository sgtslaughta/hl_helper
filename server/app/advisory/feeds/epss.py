"""EPSS (Exploit Prediction Scoring System) feed source."""

from __future__ import annotations

import gzip
import logging
import tempfile
from pathlib import Path

import httpx

from server.app.advisory.feeds import ScoreFeedSource

logger = logging.getLogger(__name__)


def parse_epss_csv(text: str) -> dict[str, float]:
    """Parse EPSS CSV text into cve -> score dict.

    Skips comment lines and headers.
    """
    scores = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("cve"):  # Skip header
            continue

        try:
            parts = line.split(",")
            if len(parts) >= 2:
                cve = parts[0].strip()
                epss = float(parts[1].strip())
                scores[cve] = epss
        except (ValueError, IndexError):
            pass

    return scores


class EPSSScoreFeed(ScoreFeedSource):
    """Sync EPSS scores from Cyentia."""

    name = "epss"

    async def sync(self) -> dict[str, float]:
        """Download and parse EPSS CSV."""
        url = "https://epss.cyentia.com/epss_scores-current.csv.gz"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "epss.csv.gz"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                tmp_path.write_bytes(response.content)

            # Decompress
            with gzip.open(tmp_path, "rt") as f:
                text = f.read()

            return parse_epss_csv(text)
