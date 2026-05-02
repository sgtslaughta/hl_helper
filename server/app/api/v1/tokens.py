"""API key admin routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from server.app.api.middleware.admin_auth import admin_required
from server.app.auth.api_key import ApiKeyService

router = APIRouter(prefix="/v1/tokens", tags=["tokens"])


class IssueRequest(BaseModel):
    """Request to issue a new API key."""

    principal_id: str
    principal_kind: str  # "user" | "service_account"
    name: str
    expires_at: datetime | None = None
    ip_allowlist: list[str] = []


class IssueResponse(BaseModel):
    """Response when issuing an API key."""

    api_key_id: str
    plaintext: str  # returned ONCE; client must store
    prefix: str
    last_4: str


class TokenSummary(BaseModel):
    """Summary of an API key (excludes plaintext)."""

    id: str
    prefix: str
    last_4: str
    name: str
    principal_id: str
    principal_kind: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


@router.post(
    "",
    response_model=IssueResponse,
    status_code=201,
    dependencies=[Depends(admin_required)],
)
async def issue_token(req: Request, body: IssueRequest) -> IssueResponse:
    """Issue a new API key.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        svc = ApiKeyService(session)
        issued = await svc.issue(
            principal_id=body.principal_id,
            principal_kind=body.principal_kind,
            name=body.name,
            expires_at=body.expires_at,
            ip_allowlist=body.ip_allowlist,
        )
        await session.commit()
    return IssueResponse(
        api_key_id=issued.api_key_id,
        plaintext=issued.plaintext,
        prefix=issued.plaintext[:8],
        last_4=issued.plaintext[-4:],
    )


@router.get(
    "",
    response_model=list[TokenSummary],
    dependencies=[Depends(admin_required)],
)
async def list_tokens(req: Request) -> list[TokenSummary]:
    """List all API keys.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    Note: plaintext is NOT returned in the list.
    """
    from sqlalchemy import select

    from server.app.models import ApiKey

    sm = req.app.state.sessionmaker
    async with sm() as session:
        rows = (await session.execute(select(ApiKey))).scalars().all()
    return [
        TokenSummary(
            id=r.id,
            prefix=r.prefix,
            last_4=r.last_4,
            name=r.name,
            principal_id=r.principal_id,
            principal_kind=r.principal_kind,
            expires_at=r.expires_at,
            revoked_at=r.revoked_at,
            last_used_at=r.last_used_at,
        )
        for r in rows
    ]


@router.delete(
    "/{api_key_id}",
    status_code=204,
    dependencies=[Depends(admin_required)],
)
async def revoke_token(req: Request, api_key_id: str) -> None:
    """Revoke an API key.

    Requires admin authentication via Authorization: Bearer <FLEET_ADMIN_TOKEN>
    """
    sm = req.app.state.sessionmaker
    async with sm() as session:
        svc = ApiKeyService(session)
        await svc.revoke(api_key_id)
        await session.commit()
