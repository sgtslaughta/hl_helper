"""RFC 9457 problem+JSON error helpers + global exception handler."""

from __future__ import annotations

import http
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
    # Drop None values (except status which is always present)
    body = {k: v for k, v in body.items() if v is not None or k == "status"}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Handle HTTPException and return problem+JSON response.

    Args:
        request: The request context.
        exc: The HTTPException.

    Returns:
        Response in problem+JSON format.
    """
    try:
        title = http.HTTPStatus(exc.status_code).phrase
    except ValueError:
        title = "HTTP error"
    detail = exc.detail if isinstance(exc.detail, str) else None
    resp = problem(
        exc.status_code,
        type_slug=str(exc.status_code),
        title=title,
        detail=detail,
        instance=str(request.url.path),
        trace_id=getattr(request.state, "trace_id", None),
    )
    # Propagate any headers the raiser set (e.g. X-MFA-Required, WWW-Authenticate).
    extra_headers = getattr(exc, "headers", None)
    if extra_headers:
        for k, v in extra_headers.items():
            resp.headers[k] = v
    return resp


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    """Handle RequestValidationError and return problem+JSON response.

    Scrubs 'input' and 'ctx.input' fields to prevent echoing attacker-supplied data.

    Args:
        request: The request context.
        exc: The RequestValidationError.

    Returns:
        Response in problem+JSON format.
    """
    trace_id = getattr(request.state, "trace_id", None)

    # Scrub input/ctx.input from errors
    errors = exc.errors()
    scrubbed_errors = []
    for error in errors:
        # Keep only loc, msg, type; drop input and ctx.input
        scrubbed_error = {}
        if "loc" in error:
            scrubbed_error["loc"] = error["loc"]
        if "msg" in error:
            scrubbed_error["msg"] = error["msg"]
        if "type" in error:
            scrubbed_error["type"] = error["type"]
        # Preserve ctx if it exists but doesn't have input
        if "ctx" in error:
            ctx = error["ctx"]
            if isinstance(ctx, dict) and "input" in ctx:
                # Remove input from ctx
                ctx = {k: v for k, v in ctx.items() if k != "input"}
            if ctx:
                scrubbed_error["ctx"] = ctx
        scrubbed_errors.append(scrubbed_error)

    return problem(
        422,
        "validation_error",
        title="Validation error",
        instance=str(request.url.path),
        errors=scrubbed_errors,
        trace_id=trace_id,
    )
