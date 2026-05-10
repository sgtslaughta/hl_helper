"""Log retention: archiving and purging of agent logs."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast, Iterator, Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from server.app.logs.models import AgentLog


class ArchiveSink(Protocol):
    """Protocol for archive storage backends."""

    def write_ndjson_gz(self, key: str, lines: Iterator[bytes]) -> None:
        """Write NDJSON lines to gzipped archive file."""
        ...

    def read_ndjson_gz(self, key: str) -> Iterator[bytes]:
        """Read NDJSON lines from gzipped archive file."""
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys matching prefix."""
        ...

    def delete(self, key: str) -> None:
        """Delete archive file by key."""
        ...

    def stat(self, key: str) -> dict[str, Any]:
        """Get file metadata: {"size": int, "mtime": datetime}."""
        ...


class LocalSink:
    """Local filesystem archive sink."""

    def __init__(self, root: Path) -> None:
        """Initialize with root directory."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_ndjson_gz(self, key: str, lines: Iterator[bytes]) -> None:
        """Write NDJSON lines to gzipped file."""
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists to handle appending
        existing_lines = []
        if path.exists():
            with gzip.open(path, "rb") as f:
                existing_lines = f.readlines()

        # Combine existing + new lines
        all_lines = existing_lines + list(lines)

        # Write as gzipped NDJSON
        with gzip.open(path, "wb") as f:
            for line in all_lines:
                f.write(line)

    def read_ndjson_gz(self, key: str) -> Iterator[bytes]:
        """Read NDJSON lines from gzipped file."""
        path = self.root / key
        if not path.exists():
            return
        with gzip.open(path, "rb") as f:
            for line in f:
                if line.strip():
                    yield line

    def list_keys(self, prefix: str) -> list[str]:
        """List all keys matching prefix."""
        prefix_path = self.root / prefix
        if not prefix_path.exists():
            return []
        keys: list[str] = []
        for p in prefix_path.rglob("*"):
            if p.is_file() and p.suffix == ".gz":
                rel = p.relative_to(self.root)
                keys.append(str(rel))
        return sorted(keys)

    def delete(self, key: str) -> None:
        """Delete file by key."""
        path = self.root / key
        if path.exists():
            path.unlink()

    def stat(self, key: str) -> dict[str, Any]:
        """Get file metadata."""
        path = self.root / key
        if not path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        st = path.stat()
        mtime_ts = st.st_mtime
        return {
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(mtime_ts, tz=timezone.utc),
        }


class S3Sink:
    """S3 archive sink (requires boto3)."""

    def __init__(self, uri: str) -> None:
        """Initialize S3 sink from s3://bucket/prefix URI."""
        try:
            import boto3
        except ImportError as e:
            raise ImportError(
                "boto3 required for S3Sink. Install with: pip install boto3"
            ) from e

        if not uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {uri}")

        parts = uri[5:].split("/", 1)
        self.bucket = parts[0]
        self.prefix = parts[1] if len(parts) > 1 else ""

        self.s3_client: Any = boto3.client("s3")

    def write_ndjson_gz(self, key: str, lines: Iterator[bytes]) -> None:
        """Write NDJSON lines to S3 gzipped file."""
        del self, key, lines  # unused in stub
        raise NotImplementedError("S3Sink.write_ndjson_gz not yet implemented")

    def read_ndjson_gz(self, key: str) -> Iterator[bytes]:
        """Read NDJSON lines from S3 gzipped file."""
        del self, key  # unused in stub
        raise NotImplementedError("S3Sink.read_ndjson_gz not yet implemented")
        yield  # make this a generator

    def list_keys(self, prefix: str) -> list[str]:
        """List keys matching prefix in S3."""
        del self, prefix  # unused in stub
        raise NotImplementedError("S3Sink.list_keys not yet implemented")

    def delete(self, key: str) -> None:
        """Delete S3 key."""
        del self, key  # unused in stub
        raise NotImplementedError("S3Sink.delete not yet implemented")

    def stat(self, key: str) -> dict[str, Any]:
        """Get S3 object metadata."""
        raise NotImplementedError("S3Sink.stat not yet implemented")


def archive_once(
    session: Session,
    sink: ArchiveSink,
    *,
    hot_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Archive logs older than hot_days and delete from hot table.

    Returns dict with:
    - archived_rows: number of rows archived
    - files_written: number of archive files written
    - host_months: list of (host_id, year, month) tuples archived
    """
    if now is None:
        now = datetime.now(timezone.utc)

    cutoff = now - timedelta(days=hot_days)
    # Ensure cutoff is naive for SQLite comparison
    cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff

    # Query for rows older than cutoff, ordered by (host_id, ts) for grouping
    stmt = (
        select(AgentLog)
        .where(AgentLog.ts < cutoff_naive)
        .order_by(AgentLog.host_id, AgentLog.ts)
    )
    rows = session.execute(stmt).scalars().all()

    if not rows:
        return {
            "archived_rows": 0,
            "files_written": 0,
            "host_months": [],
        }

    # Group rows by (host_id, year, month)
    groups: dict[tuple[str, int, int], list[AgentLog]] = {}
    for row in rows:
        host_id = cast(str, row.host_id)
        year = cast(int, row.ts.year)
        month = cast(int, row.ts.month)
        key = (host_id, year, month)
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    # Write each group to sink
    files_written = 0

    def _make_lines_gen(group_rows: list[AgentLog]) -> Iterator[bytes]:
        """Generate NDJSON lines for archive."""
        for row in group_rows:
            obj: dict[str, Any] = {
                "id": row.id,
                "host_id": row.host_id,
                "agent_id": row.agent_id,
                "agent_session_id": row.agent_session_id,
                "agent_version": row.agent_version,
                "seq": row.seq,
                "ts": row.ts.isoformat() if row.ts.tzinfo else row.ts.replace(tzinfo=timezone.utc).isoformat(),
                "level": row.level,
                "action": row.action,
                "category": row.category,
                "outcome": row.outcome,
                "duration_ns": row.duration_ns,
                "message": row.message,
                "labels": row.labels,
                "details": row.details,
                "error": row.error,
                "ingested_at": row.ingested_at.isoformat() if row.ingested_at.tzinfo else row.ingested_at.replace(tzinfo=timezone.utc).isoformat(),
            }
            yield json.dumps(obj).encode("utf-8") + b"\n"

    for (host_id, year, month), group_rows in sorted(groups.items()):
        archive_key = f"agent_logs/{year:04d}/{month:02d}/host_{host_id}.ndjson.gz"
        sink.write_ndjson_gz(archive_key, _make_lines_gen(group_rows))
        files_written += 1

    # Delete archived rows from database
    delete_stmt = delete(AgentLog).where(AgentLog.ts < cutoff_naive)
    session.execute(delete_stmt)
    session.commit()

    return {
        "archived_rows": len(rows),
        "files_written": files_written,
        "host_months": [(h, y, m) for (h, y, m) in sorted(groups.keys())],
    }


def purge_archive(
    sink: ArchiveSink,
    *,
    retention_days: int = 365,
    now: datetime | None = None,
    compliance_hold_host_ids: set[str] | None = None,
) -> int:
    """
    Delete archive files older than retention_days.

    Skips files for hosts under compliance hold.

    Returns number of files deleted.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if compliance_hold_host_ids is None:
        compliance_hold_host_ids = set()

    cutoff = now - timedelta(days=retention_days)
    deleted = 0

    # List all archive files
    keys = sink.list_keys("agent_logs/")
    for key in keys:
        # Extract host_id from key: agent_logs/YYYY/MM/host_HOST_ID.ndjson.gz
        parts = key.split("/")
        if len(parts) >= 4:
            host_part = parts[3]  # host_HOST_ID.ndjson.gz
            if host_part.startswith("host_"):
                host_id = host_part[5:].replace(".ndjson.gz", "")
                if host_id in compliance_hold_host_ids:
                    continue

        # Check file mtime
        try:
            stat = sink.stat(key)
            mtime = stat["mtime"]
            if isinstance(mtime, datetime) and mtime < cutoff:
                sink.delete(key)
                deleted += 1
        except (FileNotFoundError, KeyError):
            pass

    return deleted
