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

        async with self._sm() as session:
            await session.execute(
                delete(HostAdvisoryExposure).where(
                    HostAdvisoryExposure.host_id == host_id
                )
            )
            for d in derived:
                session.add(
                    HostAdvisoryExposure(
                        host_id=host_id,
                        advisory_id=d["advisory_id"],
                        exposure_tier=d["exposure_tier"],
                        evidence_json=json.dumps(d["evidence"]),
                        scanned_at=scanned_at,
                    )
                )
            await session.commit()

        log.info(
            "exposure.ingest host=%s rows=%d", host_id, len(derived)
        )
