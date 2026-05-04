"""FastAPI application entry point for uvicorn."""

from server.app.api.app import create_app

app = create_app()
