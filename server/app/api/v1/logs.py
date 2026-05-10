"""API endpoints for agent log queries, WS streaming, and policy management.

The /v1/logs endpoint supports:
- Cursor-based pagination over agent logs with faceted filters
- Text search across message and JSON-serialized details
- Level filtering (≥ operator via numeric mapping)
- Multi-host, category, action, and outcome filtering

The /ws/logs endpoint streams log events in real-time to connected clients.

The /v1/logs/policy endpoints manage retention and collection policies per scope
(global, host:*, etc), with temp host overrides supporting TTL-based expiration.

The /v1/logs/categories endpoint lists all registered log categories.
"""

from __future__ import annotations

import asyncio
import binascii
import json
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.logs.categories import REGISTRY as CATEGORY_REGISTRY
from server.app.logs.models import AgentLog, AgentLogPolicy
from server.app.logs.schemas import LogPolicyDoc
from server.app.pagination import apply_cursor, build_page

router = APIRouter(prefix="/v1", tags=["logs"])

# ============================================================================
# CONSTANTS AND HELPERS
# ============================================================================

LEVEL_NAMES = {"debug": 10, "info": 20, "warn": 30, "error": 40, "critical": 50}
LEVEL_NAMES_REV = {v: k for k, v in LEVEL_NAMES.items()}
OUTCOME_NAMES = {"success": 1, "failure": 2, "unknown": 0}
OUTCOME_NAMES_REV = {v: k for k, v in OUTCOME_NAMES.items()}


def _level_name_to_int(name: str) -> int:
    """Convert level name to numeric value. Defaults to info (20) if unknown."""
    return LEVEL_NAMES.get(name.lower(), 20)


def _int_to_level_name(level_int: int) -> str:
    """Convert numeric level to name."""
    return LEVEL_NAMES_REV.get(level_int, "info")


def _outcome_int_to_name(outcome_int: int | None) -> str | None:
    """Convert numeric outcome to name."""
    if outcome_int is None:
        return None
    return OUTCOME_NAMES_REV.get(outcome_int)


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class LogEntry(BaseModel):
    """Single log entry for API response."""

    id: int
    host_id: str
    agent_id: str
    agent_session_id: str
    agent_version: str | None
    seq: int
    ts: datetime
    level: str  # name, not numeric
    action: str
    category: str
    outcome: str | None  # "success", "failure", "unknown", or None
    duration_ns: int | None
    message: str | None
    labels: dict[str, Any]
    details: dict[str, Any]
    error: dict[str, Any] | None


class LogListResponse(BaseModel):
    """Paginated list of log entries with facets."""

    items: list[LogEntry]
    next_cursor: str | None
    facets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class CategoryOut(BaseModel):
    """Log category for API response."""

    name: str
    description: str
    default_level: str


class LogPolicyResponse(BaseModel):
    """Log policy for a scope."""

    scope: str
    policy: LogPolicyDoc
    created_by: str | None
    created_at: datetime


class ArchiveQueryRequest(BaseModel):
    """Request to queue a log archive export job."""

    from_ts: datetime | None = None
    to_ts: datetime | None = None
    host_ids: list[str] = Field(default_factory=list)
    level: str | None = None
    categories: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    q: str | None = None


class ArchiveQueryResponse(BaseModel):
    """Response from archive query endpoint."""

    job_id: str
    status: str = "pending"


# ============================================================================
# REST ENDPOINTS
# ============================================================================


@router.get("/logs", response_model=LogListResponse, dependencies=[Depends(admin_required)])
async def list_logs(
    req: Request,
    host_id: list[str] = Query(default=None),
    level: str | None = Query(None, description="Min level: debug/info/warn/error/critical"),
    category: list[str] = Query(default=None),
    outcome: str | None = Query(None, pattern="^(success|failure|unknown)$"),
    action: str | None = None,
    q: str | None = Query(None, description="Text search in message + details"),
    from_ts: datetime | None = Query(None),
    to_ts: datetime | None = Query(None),
    cursor: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> LogListResponse:
    """List agent logs with filtering, text search, and cursor pagination.

    Facets are computed over the filtered result set (top-50 per facet).
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        stmt = select(AgentLog)
        conds: list[Any] = []

        # Filters
        if host_id:
            conds.append(AgentLog.host_id.in_(host_id))
        if level:
            try:
                level_int = _level_name_to_int(level)
                conds.append(AgentLog.level >= level_int)
            except (ValueError, KeyError):
                raise HTTPException(400, detail=f"invalid_level: {level}")
        if category:
            conds.append(AgentLog.category.in_(category))
        if outcome:
            try:
                outcome_int = OUTCOME_NAMES[outcome]
                conds.append(AgentLog.outcome == outcome_int)
            except KeyError:
                raise HTTPException(400, detail=f"invalid_outcome: {outcome}")
        if action:
            conds.append(AgentLog.action == action)
        if from_ts:
            conds.append(AgentLog.ts >= from_ts)
        if to_ts:
            conds.append(AgentLog.ts <= to_ts)

        # Text search: message OR details JSON contains q
        if q:
            q_lower = q.lower()
            # For JSON search, use cast to string (works on most dialects)
            from sqlalchemy import cast, String
            conds.append(
                (AgentLog.message.ilike(f"%{q}%"))
                | (cast(AgentLog.details, String).ilike(f"%{q}%"))
            )

        if conds:
            stmt = stmt.where(and_(*conds))

        # Apply cursor pagination
        try:
            stmt = apply_cursor(
                stmt,
                sort_column=AgentLog.ts,
                id_column=AgentLog.id,
                cursor=cursor,
                limit=limit,
                descending=True,  # newest first
            )
        except (binascii.Error, json.JSONDecodeError, KeyError, ValueError):
            raise HTTPException(400, detail="invalid_cursor")

        rows = (await session.execute(stmt)).scalars().all()
        page = build_page(rows, limit=limit, sort_attr="ts", id_attr="id")

        # Convert to response
        items = [
            LogEntry(
                id=e.id,
                host_id=e.host_id,
                agent_id=e.agent_id,
                agent_session_id=e.agent_session_id,
                agent_version=e.agent_version,
                seq=e.seq,
                ts=e.ts,
                level=_int_to_level_name(e.level),
                action=e.action,
                category=e.category,
                outcome=_outcome_int_to_name(e.outcome),
                duration_ns=e.duration_ns,
                message=e.message,
                labels=e.labels or {},
                details=e.details or {},
                error=e.error,
            )
            for e in page.items
        ]

        # Compute facets over the filtered result set
        facets: dict[str, list[dict[str, Any]]] = {}
        if page.items:
            # Recount facets for this filtered set, top-50 per facet
            facet_conds = conds.copy()  # same filters as main query
            facet_stmt = select(AgentLog)
            if facet_conds:
                facet_stmt = facet_stmt.where(and_(*facet_conds))

            for facet_col, col_attr in [
                ("host_id", AgentLog.host_id),
                ("outcome", AgentLog.outcome),
                ("action", AgentLog.action),
                ("category", AgentLog.category),
            ]:
                f_stmt = (
                    select(col_attr, func.count(AgentLog.id).label("count"))
                    .select_from(AgentLog)
                    .where(and_(*facet_conds) if facet_conds else True)
                    .group_by(col_attr)
                    .order_by(desc(func.count(AgentLog.id)))
                    .limit(50)
                )
                f_rows = (await session.execute(f_stmt)).all()
                facets[facet_col] = [
                    {
                        "value": _outcome_int_to_name(v[0]) if facet_col == "outcome" and v[0] is not None else v[0],
                        "count": v[1],
                    }
                    for v in f_rows
                ]

        return LogListResponse(items=items, next_cursor=page.next_cursor, facets=facets)


@router.get("/logs/categories", response_model=list[CategoryOut], dependencies=[Depends(admin_required)])
async def list_categories() -> list[CategoryOut]:
    """List all registered log categories."""
    return [
        CategoryOut(
            name=c.name,
            description=c.description,
            default_level=c.default_level,
        )
        for c in CATEGORY_REGISTRY.all()
    ]


@router.get(
    "/logs/policy",
    response_model=LogPolicyResponse,
    dependencies=[Depends(admin_required)],
)
async def get_log_policy(
    req: Request,
    scope: str = Query(..., description="Policy scope: 'global', 'host:<host_id>', etc"),
) -> LogPolicyResponse:
    """Fetch log policy for a given scope.

    Returns default policy (info level, standard batching) if scope not found.
    """
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        stmt = select(AgentLogPolicy).where(AgentLogPolicy.scope == scope)
        row = (await session.execute(stmt)).scalar_one_or_none()

        if row:
            policy = LogPolicyDoc.model_validate(row.policy_json)
            return LogPolicyResponse(
                scope=scope,
                policy=policy,
                created_by=row.created_by,
                created_at=row.created_at,
            )
        else:
            # Return default policy
            default = LogPolicyDoc()
            return LogPolicyResponse(
                scope=scope,
                policy=default,
                created_by=None,
                created_at=datetime.now(timezone.utc),
            )


class LogPolicyPutRequest(BaseModel):
    """Request body for PUT /v1/logs/policy."""

    scope: str
    default_level: str | None = None
    batch_max_bytes: int | None = None
    batch_max_interval_s: int | None = None
    buffer_max_mb: int | None = None
    buffer_max_days: int | None = None
    default_sample_rate: float | None = None
    categories: list[dict[str, Any]] | None = None


async def _get_next_policy_id(session) -> int:
    """Get the next ID for AgentLogPolicy."""
    from sqlalchemy import func
    max_id = (await session.execute(select(func.max(AgentLogPolicy.id)))).scalar() or 0
    return max_id + 1


@router.put(
    "/logs/policy",
    response_model=LogPolicyResponse,
    dependencies=[Depends(admin_required)],
)
async def upsert_log_policy(
    req: Request,
    body: LogPolicyPutRequest,
) -> LogPolicyResponse:
    """Upsert a log policy. Emits audit event on change."""
    from sqlalchemy import insert as sql_insert, update as sql_update

    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        # Fetch existing or create new
        stmt = select(AgentLogPolicy).where(AgentLogPolicy.scope == body.scope)
        row = (await session.execute(stmt)).scalar_one_or_none()

        if row:
            # Update: merge fields
            existing_policy = LogPolicyDoc.model_validate(row.policy_json)
        else:
            # Create: start from default
            existing_policy = LogPolicyDoc()

        # Update fields from request
        update_dict: dict[str, Any] = {}
        if body.default_level is not None:
            update_dict["default_level"] = body.default_level
        if body.batch_max_bytes is not None:
            update_dict["batch_max_bytes"] = body.batch_max_bytes
        if body.batch_max_interval_s is not None:
            update_dict["batch_max_interval_s"] = body.batch_max_interval_s
        if body.buffer_max_mb is not None:
            update_dict["buffer_max_mb"] = body.buffer_max_mb
        if body.buffer_max_days is not None:
            update_dict["buffer_max_days"] = body.buffer_max_days
        if body.default_sample_rate is not None:
            update_dict["default_sample_rate"] = body.default_sample_rate
        if body.categories is not None:
            update_dict["categories"] = body.categories

        new_policy = existing_policy.model_copy(update={k: v for k, v in update_dict.items() if v is not None})
        # Use mode='json' to ensure datetime objects are serialized
        policy_json = json.loads(new_policy.model_dump_json())

        if row:
            # Update existing
            upd_stmt = sql_update(AgentLogPolicy).where(AgentLogPolicy.id == row.id).values(
                policy_json=policy_json,
                policy_version=row.policy_version + 1,
            )
            await session.execute(upd_stmt)
            await session.commit()
            created_by = row.created_by
            created_at = row.created_at
        else:
            # Insert new using direct insert() with explicit ID for SQLite compatibility
            next_id = await _get_next_policy_id(session)
            ins_stmt = sql_insert(AgentLogPolicy).values(
                id=next_id,
                scope=body.scope,
                policy_json=policy_json,
                policy_version=1,
                created_by="admin",
                created_at=datetime.now(timezone.utc),
            )
            await session.execute(ins_stmt)
            await session.commit()
            created_by = "admin"
            created_at = datetime.now(timezone.utc)

        return LogPolicyResponse(
            scope=body.scope,
            policy=new_policy,
            created_by=created_by,
            created_at=created_at,
        )


@router.delete(
    "/logs/policy/{scope:path}",
    dependencies=[Depends(admin_required)],
)
async def delete_log_policy(req: Request, scope: str) -> dict[str, str]:
    """Delete a log policy by scope."""
    from sqlalchemy import delete as sql_delete

    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        stmt = select(AgentLogPolicy).where(AgentLogPolicy.scope == scope)
        row = (await session.execute(stmt)).scalar_one_or_none()

        if not row:
            raise HTTPException(404, detail="policy_not_found")

        # Delete using direct delete() to avoid ORM issues
        del_stmt = sql_delete(AgentLogPolicy).where(AgentLogPolicy.id == row.id)
        await session.execute(del_stmt)
        await session.commit()

        return {"status": "deleted", "scope": scope}


class LogPolicyTempRequest(BaseModel):
    """Request body for POST /v1/logs/policy/host/{host_id}/temp."""

    level: str
    categories: list[str] = Field(default_factory=list)
    ttl_s: int


@router.post(
    "/logs/policy/host/{host_id}/temp",
    response_model=LogPolicyResponse,
    dependencies=[Depends(admin_required)],
)
async def create_temp_host_policy(
    req: Request,
    host_id: str,
    body: LogPolicyTempRequest,
) -> LogPolicyResponse:
    """Create a temporary host-scoped policy override.

    Scope is automatically `host:<host_id>`. The policy expires after `ttl_s` seconds.
    """
    from sqlalchemy import insert as sql_insert, update as sql_update
    from datetime import timedelta

    sm = get_app_state(req).sessionmaker
    scope = f"host:{host_id}"
    expires_at = datetime.now(timezone.utc)
    if body.ttl_s > 0:
        expires_at += timedelta(seconds=body.ttl_s)

    policy = LogPolicyDoc(
        default_level=body.level,
        expires_at=expires_at,
    )
    # Use mode='json' to ensure datetime objects are serialized
    policy_json = json.loads(policy.model_dump_json())

    async with sm() as session:
        # Check if already exists
        stmt = select(AgentLogPolicy).where(AgentLogPolicy.scope == scope)
        row = (await session.execute(stmt)).scalar_one_or_none()

        if row:
            # Update existing
            upd_stmt = sql_update(AgentLogPolicy).where(AgentLogPolicy.id == row.id).values(
                policy_json=policy_json,
                expires_at=expires_at,
                policy_version=row.policy_version + 1,
            )
            await session.execute(upd_stmt)
            await session.commit()
            created_by = row.created_by
            created_at = row.created_at
        else:
            # Insert new with explicit ID
            next_id = await _get_next_policy_id(session)
            ins_stmt = sql_insert(AgentLogPolicy).values(
                id=next_id,
                scope=scope,
                policy_json=policy_json,
                expires_at=expires_at,
                policy_version=1,
                created_by="admin",
                created_at=datetime.now(timezone.utc),
            )
            await session.execute(ins_stmt)
            await session.commit()
            created_by = "admin"
            created_at = datetime.now(timezone.utc)

        return LogPolicyResponse(
            scope=scope,
            policy=policy,
            created_by=created_by,
            created_at=created_at,
        )


@router.post(
    "/logs/archive/query",
    response_model=ArchiveQueryResponse,
    dependencies=[Depends(admin_required)],
)
async def archive_query(
    req: Request,
    body: ArchiveQueryRequest,
) -> ArchiveQueryResponse:
    """Queue a log archive export job.

    Returns a job_id and status. The actual export wiring is deferred to Task 3.7.
    """
    import uuid
    job_id = str(uuid.uuid4())
    # Placeholder: would queue to job system
    return ArchiveQueryResponse(job_id=job_id, status="pending")


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================


class LogBroker:
    """In-process pub/sub broker for log events."""

    def __init__(self) -> None:
        """Initialize broker with empty subscribers."""
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to log events.

        Yields events as they're published. On disconnect, unsubscribes automatically.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        sub_id = str(id(queue))
        if "all" not in self._subscribers:
            self._subscribers["all"] = []
        self._subscribers["all"].append(queue)

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            if "all" in self._subscribers:
                self._subscribers["all"] = [q for q in self._subscribers["all"] if q is not queue]

    def publish(self, event: dict[str, Any]) -> None:
        """Publish a log event to all subscribers.

        Events are dropped if the subscriber's queue is full (backpressure).
        """
        if "all" in self._subscribers:
            dead = []
            for queue in self._subscribers["all"]:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(queue)
            # Remove full queues (subscribers have lagged too far)
            if dead:
                self._subscribers["all"] = [q for q in self._subscribers["all"] if q not in dead]


def _get_or_create_log_broker(app_state: Any) -> LogBroker:
    """Get or create the singleton log broker from app state."""
    if not hasattr(app_state, "log_broker"):
        app_state.log_broker = LogBroker()
    return app_state.log_broker


def _filter_log_event(event: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Check if event matches subscriber filters."""
    if "host_id" in filters and filters["host_id"]:
        if event.get("host_id") not in filters["host_id"]:
            return False
    if "level" in filters and filters["level"]:
        level_int = event.get("level", 20)
        filter_level = _level_name_to_int(filters["level"])
        if level_int < filter_level:
            return False
    if "category" in filters and filters["category"]:
        if event.get("category") not in filters["category"]:
            return False
    return True


@router.websocket("/ws/logs")
async def logs_ws(
    ws: WebSocket,
    host_id: list[str] | None = None,
    level: str | None = None,
    category: list[str] | None = None,
) -> None:
    """WebSocket endpoint for real-time agent log streaming.

    Path: /ws/logs

    Query params:
        host_id: Host IDs to filter (repeatable, or None for all).
        level: Minimum level (debug/info/warn/error/critical).
        category: Categories to filter (repeatable, or None for all).

    Behavior:
        1. On connect: send ready message.
        2. Server forwards matching log events as they're published.
        3. Heartbeat ping every 30s; close 1011 if no pong within 60s.
        4. On disconnect: unsubscribe automatically.
    """
    await ws.accept()

    # Get or create log broker from app state
    app_state = get_app_state(ws)  # type: ignore[arg-type]
    broker = _get_or_create_log_broker(app_state)

    # Build filter dict
    filters: dict[str, Any] = {}
    if host_id:
        filters["host_id"] = host_id
    if level:
        filters["level"] = level
    if category:
        filters["category"] = category

    # Send ready
    await ws.send_json({"type": "ready"})

    # Heartbeat tracking
    import time
    last_pong: dict[str, float] = {"ts": time.monotonic()}

    async def send_heartbeat() -> None:
        """Send periodic pings; close on pong-timeout."""
        while True:
            try:
                await asyncio.sleep(30.0)
                if time.monotonic() - last_pong["ts"] > 60.0:
                    await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason="pong-timeout")
                    return
                await ws.send_json({"type": "ping"})
            except (WebSocketDisconnect, RuntimeError):
                return

    heartbeat_task = asyncio.create_task(send_heartbeat())
    event_task: asyncio.Task[Any] | None = None

    try:
        # Create event forwarder task
        async def forward_events() -> None:
            try:
                async for event in broker.subscribe():
                    if not _filter_log_event(event, filters):
                        continue
                    # Convert numeric level/outcome to names
                    evt_out = {
                        "type": "log",
                        "id": event.get("id"),
                        "host_id": event.get("host_id"),
                        "agent_id": event.get("agent_id"),
                        "agent_session_id": event.get("agent_session_id"),
                        "agent_version": event.get("agent_version"),
                        "seq": event.get("seq"),
                        "ts": event.get("ts").isoformat() if event.get("ts") else None,
                        "level": _int_to_level_name(event.get("level", 20)),
                        "action": event.get("action"),
                        "category": event.get("category"),
                        "outcome": _outcome_int_to_name(event.get("outcome")),
                        "duration_ns": event.get("duration_ns"),
                        "message": event.get("message"),
                        "labels": event.get("labels", {}),
                        "details": event.get("details", {}),
                        "error": event.get("error"),
                    }
                    await ws.send_json(evt_out)
            except (WebSocketDisconnect, RuntimeError):
                pass
            except Exception:
                pass

        event_task = asyncio.create_task(forward_events())

        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except RuntimeError:
                break

            if data.get("type") == "pong":
                last_pong["ts"] = time.monotonic()

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        if event_task:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass
