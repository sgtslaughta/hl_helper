"""ExposureHandler: ingest derived runtime exposure rows for a host."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete

log = logging.getLogger(__name__)


class ExposureHandler:
    def __init__(self, session_factory) -> None:
        self._sm = session_factory

    async def ingest(
        self,
        *,
        host_id: str,
        scanned_at: datetime,
        derived: list[dict[str, Any]],
    ) -> None:
        """Replace all host_advisory_exposure rows for host_id atomically."""
        from server.app.models.host_advisory_exposure import HostAdvisoryExposure

        # Dedupe by advisory_id: same advisory may be matched against multiple
        # packages on the host (one HostAdvisory row per pkg). Collapse to one
        # row per advisory by picking the highest tier and merging evidence.
        TIER_RANK = {
            "UNKNOWN": 0, "INSTALLED_ONLY": 1, "ACTIVE": 2, "NETWORK_EXPOSED": 3,
        }
        merged: dict[str, dict[str, Any]] = {}
        for d in derived:
            aid = d["advisory_id"]
            existing = merged.get(aid)
            if existing is None:
                merged[aid] = {
                    "exposure_tier": d["exposure_tier"],
                    "evidence": list(d.get("evidence") or []),
                }
                continue
            if TIER_RANK.get(d["exposure_tier"], 0) > TIER_RANK.get(
                existing["exposure_tier"], 0
            ):
                existing["exposure_tier"] = d["exposure_tier"]
            for ev in d.get("evidence") or []:
                if ev not in existing["evidence"]:
                    existing["evidence"].append(ev)

        async with self._sm() as session:
            await session.execute(
                delete(HostAdvisoryExposure).where(
                    HostAdvisoryExposure.host_id == host_id
                )
            )
            for aid, m in merged.items():
                session.add(
                    HostAdvisoryExposure(
                        host_id=host_id,
                        advisory_id=aid,
                        exposure_tier=m["exposure_tier"],
                        evidence_json=json.dumps(m["evidence"]),
                        scanned_at=scanned_at,
                    )
                )
            await session.commit()

        log.info(
            "exposure.ingest host=%s derived=%d unique_advisories=%d",
            host_id, len(derived), len(merged),
        )
