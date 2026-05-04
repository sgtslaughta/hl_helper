"""Token transport extraction from Authorization header or cookies.

Bearer tokens must start with 'hls_' prefix to be recognized as session tokens.
Non-hls_ bearer tokens fall through to cookie-based auth silently (for forward compatibility).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import Request

logger = logging.getLogger(__name__)


def extract_token(request: Request) -> tuple[str | None, Literal["bearer", "cookie", None]]:
    """Extract auth token from request.

    Tries in order:
    1. Authorization: Bearer hls_... header (returns "bearer")
    2. hls_session cookie (returns "cookie")

    Returns:
        (token, source) where source is "bearer", "cookie", or None if not found.
    """
    # Try Authorization header for Bearer token first (prefers bearer)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Strip "Bearer "
        if token.startswith("hls_"):
            return token, "bearer"
        # Non-hls_ bearer token ignored; fall through to cookie
        logger.debug("extract_token: non-hls_ bearer token ignored, trying cookie fallback")

    # Try hls_session cookie fallback
    session_cookie = request.cookies.get("hls_session")
    if session_cookie:
        return session_cookie, "cookie"

    return None, None
