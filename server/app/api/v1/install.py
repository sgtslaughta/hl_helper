"""Installation script endpoint."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader

router = APIRouter(prefix="/v1", tags=["install"])


@router.get("/install.sh", response_class=Response)
async def get_install_script(
    request: Request,
    token: str = "",
    server: str = "",
    grpc_endpoint: str = "",
) -> Response:
    """Get install.sh script, rendered with query params and signed.

    Args:
        token: Enrollment token (optional)
        server: Server hostname (optional, defaults to request host)

    Returns:
        Shell script with X-Install-Signature header containing base64 signature
    """
    from server.app.api.state import get_app_state

    state = get_app_state(request)

    # Default server to request host if not provided
    if not server:
        server = request.url.hostname or "localhost"

    # Load and render template
    template_dir = Path(__file__).parent.parent.parent.parent / "templates"
    # autoescape disabled: template renders POSIX shell, not HTML/XML.
    # Body is signed via Ed25519 (X-Install-Signature header) for tamper detection.
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)  # nosec B701
    template = env.get_template("install.sh.j2")
    rendered = template.render(
        token=token, server=server, SERVER=server, grpc_endpoint=grpc_endpoint
    )

    # Sign the rendered script
    rendered_bytes = rendered.encode("utf-8")
    signature = state.signing_backend.sign(rendered_bytes)
    signature_b64 = base64.b64encode(signature).decode("ascii")

    return Response(
        content=rendered,
        media_type="text/plain",
        headers={"X-Install-Signature": signature_b64},
    )
