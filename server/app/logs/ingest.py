"""Agent log ingest pipeline."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from server.app.logs.models import AgentLog
from server.app.logs.redact import redact
from server.app.logs.schemas import ECSEvent

LEVEL_MAP = {"debug": 10, "info": 20, "warn": 30, "error": 40, "critical": 50}
OUTCOME_MAP = {"success": 1, "failure": 2, "unknown": 0}


def _maybe_decompress(payload: bytes) -> bytes:
    if len(payload) >= 2 and payload[:2] == b"\x1f\x8b":
        return gzip.decompress(payload)
    return payload


def _resolve_dict(obj: Any, dictionary: dict[int, str]) -> Any:
    if isinstance(obj, str) and obj.startswith("@id:"):
        try:
            ident = int(obj[4:])
            return dictionary.get(ident, obj)
        except ValueError:
            return obj
    if isinstance(obj, list):
        return [_resolve_dict(v, dictionary) for v in obj]
    if isinstance(obj, dict):
        return {k: _resolve_dict(v, dictionary) for k, v in obj.items()}
    return obj


def _entry_to_doc(entry: Mapping[str, Any], dictionary: dict[int, str] | None) -> dict[str, Any]:
    raw = _maybe_decompress(entry["payload"])
    doc = json.loads(raw)
    if dictionary:
        doc = _resolve_dict(doc, dictionary)
    return doc


def ingest_batch(
    session,
    ws_broker,
    *,
    host_id: str,
    agent_id: str,
    agent_session_id: str,
    agent_version: str | None,
    entries: Iterable[Mapping[str, Any]],
    dictionary: dict[int, str] | None = None,
) -> int:
    rows: list[dict[str, Any]] = []
    for e in entries:
        doc = _entry_to_doc(e, dictionary)
        doc = redact(doc)
        ev = ECSEvent.model_validate(doc)
        cat = ev.event.category[0] if ev.event.category else "system"
        rows.append({
            "host_id": host_id,
            "agent_id": agent_id,
            "agent_session_id": agent_session_id,
            "agent_version": agent_version,
            "seq": ev.event.sequence,
            "ts": ev.ts,
            "level": LEVEL_MAP.get(ev.log.level, 20),
            "action": ev.event.action,
            "category": cat,
            "outcome": OUTCOME_MAP.get(ev.event.outcome or "unknown", 0),
            "duration_ns": ev.event.duration,
            "message": ev.message,
            "labels": ev.labels,
            "details": ev.details,
            "error": ev.error.model_dump() if ev.error else None,
        })
    if not rows:
        return 0

    dialect = session.bind.dialect.name
    inserted_rows: list[dict[str, Any]] = []
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(AgentLog).values(rows).on_conflict_do_nothing(index_elements=["agent_session_id", "seq"]).returning(AgentLog.seq)
        result = session.execute(stmt)
        kept = {row.seq for row in result}
        inserted_rows = [r for r in rows if r["seq"] in kept]
        session.commit()
    else:
        # SQLite: try each row individually to handle deduplication per-row
        for r in rows:
            try:
                # Don't specify 'id' - let autoincrement handle it
                stmt = insert(AgentLog).values(**r)
                session.execute(stmt)
                session.flush()  # check constraint violation before commit
                inserted_rows.append(r)
            except IntegrityError:
                session.rollback()  # undo this row only, not the whole batch
        if inserted_rows:
            session.commit()

    for r in inserted_rows:
        ws_broker.publish(host_id=r["host_id"], event=r)

    return max((r["seq"] for r in inserted_rows), default=0)
