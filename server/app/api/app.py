"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.app.api.v1.approvals import router as approvals_router
from server.app.api.v1.audit import router as audit_router
from server.app.api.v1.auth import router as auth_router
from server.app.api.v1.bindings import router as bindings_router
from server.app.api.v1.bootstrap import router as bootstrap_router
from server.app.api.v1.enroll import router as enroll_router
from server.app.api.v1.events_ws import router as events_ws_router
from server.app.api.v1.groups import router as groups_router
from server.app.api.v1.hosts import router as hosts_router
from server.app.api.v1.install import router as install_router
from server.app.api.v1.mfa import router as mfa_router
from server.app.api.v1.oidc import router as oidc_router
from server.app.api.v1 import policies
from server.app.api.v1.posture import router as posture_router
from server.app.observability.health import router as health_router
from server.app.observability.prom_endpoint import router as prom_router
from server.app.api.v1.roles import router as roles_router
from server.app.api.v1.secrets import router as secrets_router
from server.app.api.v1.settings import router as settings_router
from server.app.api.v1.task_actions import router as task_actions_router
from server.app.api.v1.tasks import router as tasks_router
from server.app.api.v1.tokens import router as tokens_router
from server.app.api.v1.user_groups import router as user_groups_router
from server.app.api.v1.users import router as users_router
from server.app.api.v1.service_accounts import router as service_accounts_router
from server.app.errors import http_exception_handler, validation_exception_handler
from server.app.idempotency import IdempotencyMiddleware
from server.app.lifespan import app_lifespan
from server.app.middleware.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    from server.app.settings.config import load_settings

    app = FastAPI(title="hl_helper", version="0.0.1", lifespan=app_lifespan)

    # Load settings for middleware configuration
    settings = load_settings()

    # Register middleware with settings-based config
    app.add_middleware(
        IdempotencyMiddleware,
        max_body_bytes=settings.idempotency_max_body_bytes,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.include_router(approvals_router)
    app.include_router(audit_router)
    app.include_router(auth_router)
    app.include_router(bindings_router)
    app.include_router(bootstrap_router)
    app.include_router(enroll_router)
    app.include_router(events_ws_router)
    app.include_router(groups_router)
    app.include_router(hosts_router)
    app.include_router(install_router)
    app.include_router(mfa_router)
    app.include_router(oidc_router)
    app.include_router(policies.update_policy_router)
    app.include_router(policies.maintenance_window_router)
    app.include_router(posture_router)
    app.include_router(health_router)
    app.include_router(prom_router)
    app.include_router(roles_router)
    app.include_router(secrets_router)
    app.include_router(settings_router)
    app.include_router(tasks_router)
    app.include_router(task_actions_router)
    app.include_router(tokens_router)
    app.include_router(users_router)
    app.include_router(user_groups_router)
    app.include_router(service_accounts_router)
    return app


