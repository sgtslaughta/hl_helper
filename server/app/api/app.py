"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.app.api.v1.enroll import router as enroll_router
from server.app.api.v1.hosts import router as hosts_router
from server.app.api.v1.install import router as install_router
from server.app.api.v1.tokens import router as tokens_router
from server.app.errors import http_exception_handler, validation_exception_handler
from server.app.lifespan import AppState, app_lifespan
from server.app.middleware.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="hl_helper", version="0.0.1", lifespan=app_lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.include_router(enroll_router)
    app.include_router(hosts_router)
    app.include_router(install_router)
    app.include_router(tokens_router)
    return app


def get_app_state(request: Request) -> AppState:
    """Get AppState from request."""
    return request.app.state.app_state  # type: ignore[no-any-return]
