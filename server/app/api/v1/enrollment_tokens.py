"""Admin enrollment-token mint/list/revoke endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.middleware.admin_auth import admin_required
from server.app.api.middleware.rate_limit import RateLimiter, rate_limit_dependency
from server.app.api.state import get_app_state
from server.app.enrollment.service import EnrollmentService
from server.app.enrollment.tokens import clamp_ttl_seconds

router = APIRouter(prefix="/v1/enrollment-tokens", tags=["enrollment-tokens"])

_mint_limiter = RateLimiter(rate_per_sec=1.0, burst=10)


class MintRequest(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    ttl_seconds: int | None = Field(default=None)


class MintResponse(BaseModel):
    token_id: str
    plaintext_token: str
    expires_at: datetime
    install_command: str


async def _get_session(request: Request) -> AsyncIterator[AsyncSession]:
    state = get_app_state(request)
    async with state.sessionmaker() as session:
        yield session


def _get_service(request: Request) -> EnrollmentService:
    return get_app_state(request).enrollment_service


def _public_origin(request: Request) -> str:
    state = get_app_state(request)
    cfg = getattr(state, "public_origin", None)
    if cfg:
        return cfg.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}"


@router.post(
    "",
    response_model=MintResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_dependency(_mint_limiter))],
)
async def mint(
    request: Request,
    body: MintRequest,
    actor: str = Depends(admin_required),
    service: EnrollmentService = Depends(_get_service),
    session: AsyncSession = Depends(_get_session),
) -> MintResponse:
    try:
        ttl_s = clamp_ttl_seconds(body.ttl_seconds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    plaintext, row = await service.issue_token(
        session,
        issued_by=actor,
        ttl=timedelta(seconds=ttl_s),
        note=body.label,
    )
    await session.commit()

    origin = _public_origin(request)
    install_command = (
        f"curl -fsSL {origin}/install.sh | sh -s -- --server={origin} --token={plaintext}"
    )
    return MintResponse(
        token_id=row.id,
        plaintext_token=plaintext,
        expires_at=row.expires_at,
        install_command=install_command,
    )
