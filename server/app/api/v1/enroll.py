"""Enrollment endpoint for agent provisioning."""

from __future__ import annotations

import base64
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.enrollment.service import (
    CsrInvalidError,
    EnrollmentService,
    TokenAlreadyRedeemedError,
    TokenExpiredError,
    TokenNotFoundError,
)
from server.app.api.middleware.rate_limit import RateLimiter, rate_limit_dependency
from server.app.errors import problem

router = APIRouter(prefix="/v1", tags=["enrollment"])

# Rate limiter: 0.5 requests per second (one every 2 seconds), burst of 5
_limiter = RateLimiter(rate_per_sec=0.5, burst=5)


class EnrollRequest(BaseModel):
    """Enrollment request."""

    token: str = Field(min_length=20)
    hostname: str = Field(min_length=1, max_length=253)
    csr_pem: str  # PEM string
    agent_pubkey_b64: str  # base64-encoded raw 32B Ed25519


class EnrollResponse(BaseModel):
    """Enrollment response."""

    host_id: str
    leaf_cert_pem: str
    intermediate_cert_pem: str
    root_cert_pem: str
    server_signing_pubkey_b64: str
    grpc_endpoint: str


# Dependency providers (can be overridden in tests)
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Get database session from app state."""
    from server.app.api.app import get_app_state

    state = get_app_state(request)
    async with state.sessionmaker() as session:
        yield session


def get_enrollment_service(request: Request) -> EnrollmentService:
    """Get enrollment service from app state."""
    from server.app.api.app import get_app_state

    state = get_app_state(request)
    return state.enrollment_service


@router.post("/enroll", response_model=EnrollResponse, dependencies=[Depends(rate_limit_dependency(_limiter))])
async def enroll(
    body: EnrollRequest,
    service: EnrollmentService = Depends(get_enrollment_service),
    session: AsyncSession = Depends(get_session),
) -> EnrollResponse:
    """Enroll an agent with a one-time token."""
    # Decode pubkey
    try:
        agent_pubkey = base64.b64decode(body.agent_pubkey_b64)
        if len(agent_pubkey) != 32:
            raise ValueError("pubkey must be 32 bytes")
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid agent pubkey") from e

    # Decode CSR
    try:
        csr_pem = body.csr_pem.encode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid CSR") from e

    # Call service.redeem
    try:
        result = await service.redeem(
            session,
            token_plaintext=body.token,
            csr_pem=csr_pem,
            hostname=body.hostname,
            agent_pubkey=agent_pubkey,
        )
    except (TokenNotFoundError, TokenExpiredError, TokenAlreadyRedeemedError):
        # Return uniform 401 for all token failures (oracle mitigation)
        return problem(401, "invalid_or_expired_token", title="invalid_or_expired_token")
    except CsrInvalidError:
        raise HTTPException(status_code=400, detail="invalid CSR")

    # Commit
    await session.commit()

    # Return response
    server_signing_pubkey_b64 = base64.b64encode(result.server_signing_pubkey).decode("ascii")

    return EnrollResponse(
        host_id=result.host_id,
        leaf_cert_pem=result.leaf_cert_pem.decode("utf-8"),
        intermediate_cert_pem=result.intermediate_cert_pem.decode("utf-8"),
        root_cert_pem=result.root_cert_pem.decode("utf-8"),
        server_signing_pubkey_b64=server_signing_pubkey_b64,
        grpc_endpoint=result.grpc_endpoint,
    )
