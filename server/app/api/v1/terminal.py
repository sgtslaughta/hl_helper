"""Terminal API: session metadata + asciicast recording retrieval (C9)."""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.state import get_app_state
from server.app.terminal.models import TerminalRecording

router = APIRouter(prefix="/v1/terminal", tags=["terminal"])
log = structlog.get_logger(__name__)


class SessionOut(BaseModel):
    """Terminal session response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(...)
    host_id: str = Field(...)
    user_id: str = Field(...)
    state: str = Field(default="pending")


class RecordingOut(BaseModel):
    """Terminal recording metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    host_id: str
    user_id: str
    sha256: str = ""
    size_bytes: int = 0


@router.post("/sessions", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_session(actor: str = Depends(admin_required)) -> dict[str, str]:
    """Create a new terminal session.

    The full WebSocket bridge to the agent's gRPC PTY stream is implemented
    in C9 phase 2. This endpoint exists so the UI surfaces a stable contract.
    """
    log.info("terminal.session.create.todo", actor=actor)
    raise HTTPException(status_code=501, detail="terminal websocket bridge pending (C9 phase 2)")


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(actor: str = Depends(admin_required)) -> list[SessionOut]:
    """List active terminal sessions.

    Active sessions are tracked in-memory in the session manager (not yet
    implemented). Returns empty list until C9 phase 2.
    """
    return []


@router.get("/recordings", response_model=list[RecordingOut])
async def list_recordings(
    req: Request,
    actor: str = Depends(admin_required),
) -> list[RecordingOut]:
    """List asciicast recordings stored on the server."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        result = await session.execute(
            select(TerminalRecording).order_by(TerminalRecording.started_at.desc())
        )
        return [RecordingOut.model_validate(r) for r in result.scalars().all()]


@router.get("/recordings/{recording_id}")
async def get_recording(
    recording_id: str,
    req: Request,
    actor: str = Depends(admin_required),
) -> FileResponse:
    """Stream an asciicast v2 file by recording id."""
    sm = get_app_state(req).sessionmaker
    async with sm() as session:
        rec = await session.get(TerminalRecording, recording_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    path = Path(rec.asciicast_path)
    if not path.exists() or not os.access(path, os.R_OK):
        raise HTTPException(status_code=410, detail="recording file missing")
    return FileResponse(path, media_type="application/x-asciicast", filename=path.name)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kill_session(session_id: str, actor: str = Depends(admin_required)) -> Response:
    """Send the kill switch to an active session.

    The agent-side dispatch is implemented in C9 phase 2; this endpoint logs
    the intent and returns 204 so the UI can wire up the button.
    """
    log.warning("terminal.session.kill.todo", actor=actor, session_id=session_id)
    return Response(status_code=204)
