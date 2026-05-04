"""Prometheus scrape endpoint for fleet metrics.

@brief Exposes ``GET /v1/metrics`` returning Prometheus text exposition
       format. Protected by admin Bearer-token authentication and gated
       by the ``FLEET_METRICS_ENABLED`` setting.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from prometheus_client import generate_latest

from server.app.api.middleware.admin_auth import admin_required
from server.app.observability.metrics import get_registry
from server.app.settings.config import load_settings

router = APIRouter()

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get(
    "/v1/metrics",
    summary="Prometheus metrics scrape endpoint",
    response_class=Response,
)
async def prometheus_metrics(_actor: str = Depends(admin_required)) -> Response:
    """@brief Serve Prometheus text format metrics.

    @param _actor  Authenticated admin principal (injected by dependency).
    @return Plain-text Prometheus exposition payload.
    @raises HTTPException 404 when ``FLEET_METRICS_ENABLED`` is false.
    """
    settings = load_settings()
    if not settings.metrics_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics endpoint is disabled",
        )

    payload = generate_latest(get_registry())
    return Response(content=payload, media_type=PROMETHEUS_CONTENT_TYPE)
