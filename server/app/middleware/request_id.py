"""Request-ID middleware: read or generate a trace_id and attach to request.state."""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to read or generate request ID and attach to response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with request ID.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response with X-Request-ID header.
        """
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.trace_id = rid
        response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
