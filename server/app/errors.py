"""RFC 9457 problem+JSON error helpers + global exception handler."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException


def problem(
    status: int,
    type_slug: str,
    title: str | None = None,
    detail: str | None = None,
    **extra: Any,
) -> JSONResponse:
    """Create RFC 9457 problem+JSON response.

    Args:
        status: HTTP status code.
        type_slug: Error type slug (will be prefixed with /errors/).
        title: Human-readable title (defaults to slug title-cased).
        detail: Additional detail message.
        **extra: Additional fields to include in response.

    Returns:
        JSONResponse with problem+json media type.
    """
    body: dict[str, Any] = {
        "type": f"/errors/{type_slug}",
        "title": title or type_slug.replace("_", " ").title(),
        "status": status,
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Handle HTTPException and return problem+JSON response.

    Args:
        request: The request context.
        exc: The HTTPException.

    Returns:
        Response in problem+JSON format.
    """
    trace_id = getattr(request.state, "trace_id", None)
    return problem(
        exc.status_code,
        type_slug=str(exc.status_code),
        title=exc.detail if isinstance(exc.detail, str) else "HTTP error",
        detail=str(exc.detail) if not isinstance(exc.detail, str) else None,
        instance=str(request.url.path),
        trace_id=trace_id,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    """Handle RequestValidationError and return problem+JSON response.

    Args:
        request: The request context.
        exc: The RequestValidationError.

    Returns:
        Response in problem+JSON format.
    """
    trace_id = getattr(request.state, "trace_id", None)
    return problem(
        422,
        "validation_error",
        title="Validation error",
        instance=str(request.url.path),
        errors=exc.errors(),
        trace_id=trace_id,
    )
