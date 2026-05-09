"""Tests for Trivy container scanner bridge."""

from __future__ import annotations

from unittest import mock
from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.models.host import Host
from server.app.models.host_container import HostContainer
from server.app.advisory.container_scanner import TrivyClient, scan_host_containers


@pytest.mark.asyncio
async def test_trivy_unavailable_returns_zero(sm: async_sessionmaker) -> None:
    """scan_host_containers returns 0 when trivy is not available."""
    host_id = str(uuid4())

    # Create host
    async with sm() as session:
        host = Host(
            id=host_id,
            hostname="test-host",
            agent_pubkey=b"\x00" * 32,
            agent_version="0.4.0",
        )
        session.add(host)
        await session.commit()

    # Create container
    async with sm() as session:
        container = HostContainer(
            host_id=host_id,
            container_id="abc123",
            name="test-container",
            image_ref="docker.io/library/nginx:latest",
            image_digest="sha256:abc",
            state="running",
            engine="docker",
        )
        session.add(container)
        await session.commit()

    # Mock shutil.which to return None (trivy unavailable)
    with mock.patch("server.app.advisory.container_scanner.shutil.which", return_value=None):
        count = await scan_host_containers(sm, host_id)

    assert count == 0


@pytest.mark.asyncio
async def test_scan_image_caches_results() -> None:
    """TrivyClient caches scan results by image_ref."""
    client = TrivyClient()

    # Mock subprocess to return canned JSON
    canned_json = """
    {
      "Results": [
        {
          "Vulnerabilities": [
            {
              "VulnerabilityID": "CVE-2024-1111",
              "Severity": "HIGH",
              "PkgName": "openssl",
              "InstalledVersion": "1.1.1",
              "FixedVersion": "1.1.2",
              "CVSS": {"ghsa": {"V3Score": 7.5}}
            }
          ]
        }
      ]
    }
    """

    async def mock_create_subprocess_exec(*args, **kwargs):
        mock_proc = mock.AsyncMock()
        mock_proc.communicate = mock.AsyncMock(return_value=(canned_json.encode(), b""))
        mock_proc.returncode = 0
        return mock_proc

    # First call: fetch from subprocess
    with mock.patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
        result1 = await client.scan_image("docker.io/library/nginx:latest")

    # Second call: should be from cache (subprocess not called again)
    call_count = 0

    async def mock_create_subprocess_exec_counted(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_proc = mock.AsyncMock()
        mock_proc.communicate = mock.AsyncMock(return_value=(canned_json.encode(), b""))
        mock_proc.returncode = 0
        return mock_proc

    with mock.patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec_counted):
        result2 = await client.scan_image("docker.io/library/nginx:latest")

    # No subprocess call on second invocation
    assert call_count == 0
    # Results should be identical
    assert result1 == result2
    assert len(result1) >= 0
