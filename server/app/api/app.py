"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from server.app.api.v1.enroll import router as enroll_router


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="hl_helper", version="0.0.1")
    app.include_router(enroll_router)
    return app
