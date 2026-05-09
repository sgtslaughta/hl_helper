"""Advisory feed admin endpoints.

GET  /v1/advisories/feeds/status      — per-feed snapshot for the UI card.
POST /v1/advisories/feeds/sync        — admin-only manual trigger; enqueues
                                        a sync run on the worker. Returns 202.
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.advisory.worker import FEED_NAMES

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/advisories/feeds", tags=["advisories"])


class FeedStatusOut(BaseModel):
    feed: str
    last_sync_at: str | None = None
    last_count: int = 0
    last_error: str | None = None
    next_scheduled_at: str | None = None
    in_progress: bool = False


class FeedStatusResponse(BaseModel):
    feeds: list[FeedStatusOut]


class FeedSyncResponse(BaseModel):
    status: Literal["accepted", "queue_full", "disabled"]
    feeds: list[str]


def _worker(request: Request) -> Any:
    state = get_app_state(request)
    worker = getattr(state, "advisory_worker", None)
    if worker is None:
        raise HTTPException(status_code=503, detail="advisory worker not available")
    return worker


@router.get("/status", response_model=FeedStatusResponse)
async def get_feed_status(
    request: Request,
    _: str = Depends(admin_required),
) -> FeedStatusResponse:
    """Return current per-feed status (last sync, count, error, in-progress)."""
    state = get_app_state(request)
    worker = getattr(state, "advisory_worker", None)
    if worker is None:
        # Worker disabled (advisory_enabled=false or catalog missing): synthesise
        # an empty rollup so the UI can render rather than 503ing.
        return FeedStatusResponse(
            feeds=[FeedStatusOut(feed=name) for name in FEED_NAMES]
        )
    rows = await worker.get_status()
    return FeedStatusResponse(feeds=[FeedStatusOut(**r) for r in rows])


@router.post("/sync", response_model=FeedSyncResponse, status_code=202)
async def trigger_feed_sync(
    request: Request,
    feed: Literal["osv", "epss", "kev", "all"] = Query("all"),
    _: str = Depends(admin_required),
) -> FeedSyncResponse:
    """Enqueue a manual sync on the worker. Returns 202 even if already in flight."""
    worker = _worker(request)
    targets: list[str] = list(FEED_NAMES) if feed == "all" else [feed]
    enqueued: list[str] = []
    for name in targets:
        if worker.enqueue_feed_sync(name, trigger="manual"):
            enqueued.append(name)
    if not enqueued:
        return FeedSyncResponse(status="queue_full", feeds=targets)
    return FeedSyncResponse(status="accepted", feeds=enqueued)
