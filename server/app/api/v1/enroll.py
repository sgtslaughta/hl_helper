"""Enrollment endpoint for agent provisioning."""

from __future__ import annotations

import base64
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.enrollment.service import (
    CsrInvalidError,
    EnrollmentService,
    TokenAlreadyRedeemedError,
    TokenExpiredError,
    TokenNotFoundError,
)

router = APIRouter(prefix="/v1", tags=["enrollment"])


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


# Dependency providers (will be overridden in tests)
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session. Override in tests."""
    raise NotImplementedError("get_session must be provided by app startup")


def get_enrollment_service() -> EnrollmentService:
    """Get enrollment service. Override in tests."""
    raise NotImplementedError("get_enrollment_service must be provided by app startup")


@router.post("/enroll", response_model=EnrollResponse)
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
    except TokenNotFoundError:
        raise HTTPException(status_code=404, detail="enrollment token not found")
    except TokenExpiredError:
        raise HTTPException(status_code=410, detail="enrollment token expired")
    except TokenAlreadyRedeemedError:
        raise HTTPException(status_code=409, detail="enrollment token already redeemed")
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
