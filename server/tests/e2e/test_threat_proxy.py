"""Threat-model E2E test: install script proxy-terminate diagnostic (Phase 8)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def test_proxy_terminate_agent_port_diagnostic() -> None:
    """install.sh emits clear error when gRPC port unreachable (proxy mis-config)."""
    template_dir = Path(__file__).resolve().parents[2] / "app" / ".." / "templates"
    template_dir = (Path(__file__).resolve().parents[2] / "templates").resolve()
    env = Environment(loader=FileSystemLoader(template_dir))
    rendered = env.get_template("install.sh.j2").render(
        token="t", server="host", grpc_endpoint="grpc.example:50051"
    )
    assert "gRPC port" in rendered
    assert "unreachable" in rendered
    assert "HTTP/2 end-to-end" in rendered
    assert "nc -z" in rendered
    assert "exit 1" in rendered


def test_install_script_ca_pinning_and_cosign() -> None:
    """install.sh includes CA pinning and cosign binary verification."""
    template_dir = (Path(__file__).resolve().parents[2] / "templates").resolve()
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    ca_pem = "-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----"
    pubkey_pem = "-----BEGIN PUBLIC KEY-----\nMCow...\n-----END PUBLIC KEY-----"
    rendered = env.get_template("install.sh.j2").render(
        token="t",
        server="host",
        grpc_endpoint="grpc.example:50051",
        server_ca_pem=ca_pem,
        release_signing_pubkey_pem=pubkey_pem,
    )
    # Verify CA cert is embedded
    assert ca_pem in rendered
    # Verify curl uses --cacert for enrollment
    assert "--cacert" in rendered
    # Verify cosign verification is present
    assert "cosign" in rendered
    # Verify sudoers validation
    assert "visudo" in rendered
    # Verify systemd unit validation
    assert "systemd-analyze" in rendered
    # Verify enable and start
    assert "systemctl enable" in rendered
    assert "Installation complete" in rendered
