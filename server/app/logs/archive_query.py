"""Archive query manager for searching archived logs."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from server.app.logs.retention import ArchiveSink


class ArchiveQueryManager:
    """Manages async queries over archived logs."""

    def __init__(self, sink: ArchiveSink) -> None:
        """Initialize with archive sink."""
        self.sink = sink
        self._jobs: dict[str, dict[str, Any]] = {}

    async def submit(
        self,
        *,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        host_ids: list[str] | None = None,
        level: int | None = None,
        action: str | None = None,
        q: str | None = None,
    ) -> str:
        """
        Submit an archive query job.

        Returns job_id string.
        """
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "state": "pending",
            "results": [],
            "error": None,
        }

        # Kick off async processing
        asyncio.create_task(
            self._process_query(job_id, from_ts, to_ts, host_ids, level, action, q)
        )

        return job_id

    def status(self, job_id: str) -> dict[str, Any]:
        """Get job status."""
        if job_id not in self._jobs:
            return {
                "state": "error",
                "error": "Job not found",
                "results": [],
            }
        return self._jobs[job_id]

    async def _process_query(
        self,
        job_id: str,
        from_ts: datetime | None,
        to_ts: datetime | None,
        host_ids: list[str] | None,
        level: int | None,
        action: str | None,
        q: str | None,
    ) -> None:
        """Process query asynchronously."""
        try:
            self._jobs[job_id]["state"] = "running"
            results = []

            # List all archive files
            keys = self.sink.list_keys("agent_logs/")

            for key in keys:
                # Filter by host_ids if specified
                if host_ids:
                    parts = key.split("/")
                    if len(parts) >= 4:
                        host_part = parts[3]
                        if host_part.startswith("host_"):
                            host_id = host_part[5:].replace(".ndjson.gz", "")
                            if host_id not in host_ids:
                                continue

                # Stream and filter lines from archive file
                for line in self.sink.read_ndjson_gz(key):
                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue

                    # Apply filters
                    if from_ts and obj.get("ts"):
                        try:
                            line_ts = datetime.fromisoformat(obj["ts"])
                            if line_ts < from_ts:
                                continue
                        except (ValueError, TypeError):
                            pass

                    if to_ts and obj.get("ts"):
                        try:
                            line_ts = datetime.fromisoformat(obj["ts"])
                            if line_ts > to_ts:
                                continue
                        except (ValueError, TypeError):
                            pass

                    if level is not None and obj.get("level") != level:
                        continue

                    if action is not None and obj.get("action") != action:
                        continue

                    if q is not None:
                        # Simple substring search in message
                        if q not in obj.get("message", ""):
                            continue

                    results.append(obj)

                    # Yield to event loop
                    await asyncio.sleep(0)

            self._jobs[job_id]["state"] = "complete"
            self._jobs[job_id]["results"] = results

        except Exception as e:
            self._jobs[job_id]["state"] = "error"
            self._jobs[job_id]["error"] = str(e)
