"""Validate server Dockerfile structure and security properties."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_PATH = ROOT / "deploy/server/Dockerfile"


def test_dockerfile_exists():
    """Server Dockerfile must exist."""
    assert DOCKERFILE_PATH.is_file()


def test_dockerfile_multi_stage():
    """Dockerfile must use multi-stage build."""
    text = DOCKERFILE_PATH.read_text()
    assert text.count("FROM") >= 2, "Multi-stage build requires at least 2 FROM directives"


def test_dockerfile_non_root_user():
    """Runtime stage must run as non-root user."""
    text = DOCKERFILE_PATH.read_text()
    assert "USER" in text, "USER directive required"
    assert "uid 10001" in text or "10001" in text, "Non-root user with uid 10001 expected"


def test_dockerfile_no_dangerous_patterns():
    """Reject curl|sh, ADD http, --no-verify, and similar anti-patterns."""
    text = DOCKERFILE_PATH.read_text()
    dangerous = [
        r"curl\s+.*\|\s*sh",
        r"curl\s+.*\|\s*bash",
        r"\bADD\s+http",
        r"--no-verify",
    ]
    for pattern in dangerous:
        assert not re.search(pattern, text, re.IGNORECASE), f"Dangerous pattern found: {pattern}"


def test_dockerfile_workdir_set():
    """WORKDIR must be set to /app."""
    text = DOCKERFILE_PATH.read_text()
    assert "WORKDIR /app" in text, "WORKDIR /app expected"


def test_dockerfile_expose_ports():
    """Must EXPOSE port 8000 for HTTP."""
    text = DOCKERFILE_PATH.read_text()
    assert "EXPOSE" in text, "EXPOSE directive required"
    assert "8000" in text, "Port 8000 (HTTP) must be exposed"


def test_dockerfile_healthcheck_present():
    """HEALTHCHECK directive must be present."""
    text = DOCKERFILE_PATH.read_text()
    assert "HEALTHCHECK" in text, "HEALTHCHECK directive required"
    assert "/healthz" in text or "/v1/observability/health" in text, \
        "Healthcheck must probe /healthz or /v1/observability/health"


def test_dockerfile_entrypoint_present():
    """ENTRYPOINT must use uvicorn."""
    text = DOCKERFILE_PATH.read_text()
    assert "ENTRYPOINT" in text, "ENTRYPOINT directive required"
    assert "uvicorn" in text, "Must use uvicorn as entrypoint"
