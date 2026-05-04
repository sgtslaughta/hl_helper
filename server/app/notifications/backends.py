"""Built-in notification backends: webhook (HTTP POST) + SMTP."""

from __future__ import annotations

import asyncio
import json
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx
import structlog

from server.app.notifications.dispatcher import NotificationMessage, NotificationResult

log = structlog.get_logger(__name__)


async def webhook_backend(
    config: dict[str, Any], message: NotificationMessage
) -> NotificationResult:
    """POST a JSON payload to a configurable webhook URL.

    Config keys:
      - url (required): destination URL
      - timeout_s (optional, default 10)
      - headers (optional dict)
    """
    url = config.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return NotificationResult(ok=False, provider="webhook", detail="invalid_url")

    timeout = float(config.get("timeout_s", 10))
    headers = config.get("headers") or {}
    payload = {
        "title": message.title,
        "body": message.body,
        "severity": message.severity,
        "metadata": message.metadata,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=headers)
        if 200 <= r.status_code < 300:
            return NotificationResult(ok=True, provider="webhook", detail=f"status={r.status_code}")
        return NotificationResult(
            ok=False, provider="webhook", detail=f"status={r.status_code} body={r.text[:200]}"
        )
    except httpx.HTTPError as exc:
        return NotificationResult(ok=False, provider="webhook", detail=f"http_error: {exc}")


async def smtp_backend(
    config: dict[str, Any], message: NotificationMessage
) -> NotificationResult:
    """Send via SMTP. Config keys:

      - host (required)
      - port (default 587)
      - from_addr (required)
      - to_addrs (required: list[str] or comma-separated str)
      - username, password (optional; STARTTLS auth if both set)
      - use_tls (default True)
      - timeout_s (default 10)
    """
    host = config.get("host")
    from_addr = config.get("from_addr")
    to = config.get("to_addrs")
    if not host or not from_addr or not to:
        return NotificationResult(
            ok=False, provider="smtp", detail="missing_required_config"
        )

    port = int(config.get("port", 587))
    timeout = float(config.get("timeout_s", 10))
    use_tls = bool(config.get("use_tls", True))
    username = config.get("username")
    password = config.get("password")

    if isinstance(to, str):
        to_list = [a.strip() for a in to.split(",") if a.strip()]
    elif isinstance(to, list):
        to_list = list(to)
    else:
        return NotificationResult(ok=False, provider="smtp", detail="invalid_to_addrs")

    msg = EmailMessage()
    msg["Subject"] = message.title
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    msg.set_content(message.body)
    if message.metadata:
        msg.add_alternative(
            f"<pre>{json.dumps(message.metadata, indent=2)}</pre>", subtype="html"
        )

    def _send() -> None:
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            if use_tls:
                s.starttls()
            if username and password:
                s.login(username, password)
            s.send_message(msg)

    try:
        await asyncio.to_thread(_send)
        return NotificationResult(ok=True, provider="smtp", detail=f"sent_to={len(to_list)}")
    except (smtplib.SMTPException, OSError) as exc:
        return NotificationResult(ok=False, provider="smtp", detail=f"smtp_error: {exc}")
