"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request

from server.app.api.v1.enroll import router as enroll_router
from server.app.api.v1.hosts import router as hosts_router
from server.app.api.v1.install import router as install_router
from server.app.lifespan import AppState, app_lifespan


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="hl_helper", version="0.0.1", lifespan=app_lifespan)
    app.include_router(enroll_router)
    app.include_router(hosts_router)
    app.include_router(install_router)
    return app


def get_app_state(request: Request) -> AppState:
    """Get AppState from request."""
    return request.app.state.app_state  # type: ignore[no-any-return]
