"""Common FastAPI dependencies. Auth principal stubbed until C3."""

from __future__ import annotations

from fastapi import Request


async def current_principal(request: Request) -> None:
    """Placeholder: returns None until C3 wires API keys + sessions.

    C2 RBAC dependency (deps_rbac.py, Task 3.3) will require a real principal;
    that task can replace this stub with the real implementation.

    Args:
        request: The request context.

    Returns:
        None (stub).
    """
    return None
