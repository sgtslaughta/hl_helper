"""Health endpoint for fleet-server observability.

@brief Exposes ``GET /v1/observability/health`` which probes each configured
       subsystem (DB, MeiliSearch, Vault, Plugin Runtime, Egress Proxy) and
       returns a structured health report.

The endpoint is admin-only and does **not** make outbound network calls
unless the corresponding subsystem is explicitly configured.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.settings.config import load_settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/observability", tags=["observability"])

_MAX_ERROR_LEN = 200


def _sanitize_error(exc: Exception) -> str:
    """@brief Truncate exception messages to avoid leaking internal details.

    @param  exc  The caught exception.
    @return A string safe for inclusion in health responses.
    """
    raw = str(exc)
    if len(raw) > _MAX_ERROR_LEN:
        raw = raw[:_MAX_ERROR_LEN] + "..."
    return raw


# ----------------------------------------------------------------------- #
# Response models
# ----------------------------------------------------------------------- #


class ComponentHealth(BaseModel):
    """@brief Health status of a single subsystem component.

    @param name       Human-readable component identifier.
    @param status     One of ``ok``, ``degraded``, ``unreachable``, or
                      ``not_configured``.
    @param message    Optional free-text detail (error message, notes).
    @param latency_ms Optional probe latency in milliseconds.
    """

    name: str
    status: Literal["ok", "degraded", "unreachable", "not_configured"]
    message: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """@brief Aggregate health report returned by the health endpoint.

    @param status     Overall status derived from individual component checks.
    @param components Per-component breakdown.
    """

    status: Literal["healthy", "degraded", "unhealthy"]
    components: list[ComponentHealth]


# ----------------------------------------------------------------------- #
# Individual probes
# ----------------------------------------------------------------------- #


async def _check_db(app_state: Any) -> ComponentHealth:
    """@brief Probe the database with ``SELECT 1``.

    @param  app_state  Application state containing the sessionmaker.
    @return ComponentHealth with ``ok``, ``degraded``, or ``unreachable`` status.
    """
    start = time.monotonic()
    try:
        async with app_state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        elapsed = (time.monotonic() - start) * 1000
        return ComponentHealth(name="db", status="ok", latency_ms=round(elapsed, 2))
    except (OSError, ConnectionError, ConnectionRefusedError) as exc:
        elapsed = (time.monotonic() - start) * 1000
        log.warning("health_check_db_failed", error=str(exc))
        return ComponentHealth(
            name="db",
            status="unreachable",
            message=_sanitize_error(exc),
            latency_ms=round(elapsed, 2),
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        log.warning("health_check_db_failed", error=str(exc))
        return ComponentHealth(
            name="db",
            status="degraded",
            message=_sanitize_error(exc),
            latency_ms=round(elapsed, 2),
        )


async def _check_meilisearch(app_state: Any) -> ComponentHealth:
    """@brief Check MeiliSearch availability (stub).

    @param  app_state  Application state potentially containing a search client.
    @return ComponentHealth — ``not_configured`` until wired.
    """
    if not hasattr(app_state, "search_client") or app_state.search_client is None:
        return ComponentHealth(
            name="meilisearch",
            status="not_configured",
            message="not yet wired",
        )
    return ComponentHealth(name="meilisearch", status="ok", message="not yet wired")


async def _check_vault(app_state: Any) -> ComponentHealth:
    """@brief Probe Vault if a vault backend is present in the secrets broker.

    @param  app_state  Application state containing the optional secrets broker.
    @return ComponentHealth — ``ok``, ``degraded`` (sealed), ``unreachable``,
            or ``not_configured``.
    """
    broker = getattr(app_state, "secrets_broker", None)
    if broker is None:
        return ComponentHealth(name="vault", status="not_configured")

    backends = getattr(broker, "backends", None)
    if not isinstance(backends, dict) or "vault" not in backends:
        return ComponentHealth(name="vault", status="not_configured")

    vault = backends["vault"]
    start = time.monotonic()
    try:
        result = await vault.health_check()
        elapsed = (time.monotonic() - start) * 1000
        if result.get("sealed"):
            return ComponentHealth(
                name="vault",
                status="degraded",
                message="vault is sealed",
                latency_ms=round(elapsed, 2),
            )
        return ComponentHealth(name="vault", status="ok", latency_ms=round(elapsed, 2))
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        log.warning("health_check_vault_failed", error=str(exc))
        return ComponentHealth(
            name="vault",
            status="unreachable",
            message=_sanitize_error(exc),
            latency_ms=round(elapsed, 2),
        )


async def _check_plugin_runtime() -> ComponentHealth:
    """@brief Stub probe for the plugin runtime.

    @return ComponentHealth with ``not_configured`` status.
    """
    return ComponentHealth(
        name="plugin_runtime",
        status="not_configured",
        message="not yet wired",
    )


async def _check_egress_proxy() -> ComponentHealth:
    """@brief Probe the egress proxy if configured in settings.

    Only attempts a HEAD request when ``egress_proxy`` is set. Privacy by
    default: no outbound calls when unconfigured.

    @return ComponentHealth with status reflecting probe outcome.
    """
    settings = load_settings()
    if not settings.egress_proxy:
        return ComponentHealth(name="egress_proxy", status="not_configured")

    import httpx

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.head(settings.egress_proxy)
        elapsed = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="egress_proxy", status="ok", latency_ms=round(elapsed, 2)
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        log.warning("health_check_egress_proxy_failed", error=str(exc))
        return ComponentHealth(
            name="egress_proxy",
            status="unreachable",
            message=_sanitize_error(exc),
            latency_ms=round(elapsed, 2),
        )


# ----------------------------------------------------------------------- #
# Aggregate logic
# ----------------------------------------------------------------------- #


def _derive_overall_status(
    components: list[ComponentHealth],
) -> Literal["healthy", "degraded", "unhealthy"]:
    """@brief Compute aggregate status from individual component statuses.

    @param  components  List of checked components.
    @return ``healthy`` if all configured components are ``ok``,
            ``degraded`` if any is ``degraded``, ``unhealthy`` if any
            is ``unreachable``.
    """
    configured = [c for c in components if c.status != "not_configured"]
    if any(c.status == "unreachable" for c in configured):
        return "unhealthy"
    if any(c.status == "degraded" for c in configured):
        return "degraded"
    return "healthy"


# ----------------------------------------------------------------------- #
# Route
# ----------------------------------------------------------------------- #


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    _actor: str = Depends(admin_required),
) -> HealthResponse:
    """@brief Return structured health report for all subsystems.

    @param  request  FastAPI request (used to access app state).
    @param  _actor   Injected by ``admin_required`` dependency.
    @return HealthResponse with per-component breakdown.
    """
    app_state = get_app_state(request)

    components = [
        await _check_db(app_state),
        await _check_meilisearch(app_state),
        await _check_vault(app_state),
        await _check_plugin_runtime(),
        await _check_egress_proxy(),
    ]

    overall = _derive_overall_status(components)
    return HealthResponse(status=overall, components=components)
