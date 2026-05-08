"""Tests for /v1/agent-releases endpoint suite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient

from server.app.api.app import create_app
from server.app.api.v1.agent_releases import make_download_token
from server.app.models.agent_release import AgentRelease, ReleaseChannel, ReleaseStatus
from server.tests._helpers.app_state import make_test_app_state


@pytest.fixture
def ci_token() -> str:
    """Return a CI token."""
    return "test-ci-token"


@pytest.fixture
def mock_ci_token(ci_token: str):
    """Mock the CI token in environment."""
    with mock.patch.dict("os.environ", {"HL_CI_TOKEN": ci_token}):
        yield ci_token


@pytest.fixture
def mock_admin_token():
    """Mock the admin token in settings."""
    with mock.patch("server.app.api.middleware.admin_auth.load_settings") as mock_load:
        from pydantic import SecretStr
        settings = mock.MagicMock()
        settings.admin_token = SecretStr("test-admin-token")
        mock_load.return_value = settings
        yield mock_load


@pytest.fixture
def admin_auth() -> dict[str, str]:
    """Return auth header for admin."""
    return {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
def ca_fixture(tmp_path: Path):
    """Return bootstrapped CA for tests."""
    from server.app.crypto.ca import InternalCA
    return InternalCA.bootstrap(tmp_path / "ca")


@pytest.mark.asyncio
async def test_upload_release_creates_signed_manifest(
    sm, mock_ci_token, ca_fixture, tmp_path
):
    """Upload release creates manifest with valid signature."""
    binary = b"\x7fELF" + b"\x00" * 1024
    sha = hashlib.sha256(binary).hexdigest()

    files = {"binary": ("hl-agent", binary, "application/octet-stream")}
    data = {
        "version": "0.4.2",
        "channel": "stable",
        "os": "linux",
        "arch": "amd64",
        "min_prev_version": "0.3.0",
    }

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    dist_dir = tmp_path / "agent-dist"
    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                "/v1/agent-releases",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {mock_ci_token}"},
            )

    assert r.status_code == 201
    body = r.json()
    assert body["sha256"] == sha
    assert body["status"] == "published"
    assert body["version"] == "0.4.2"
    assert body["channel"] == "stable"

    # Verify manifest signature
    manifest = json.loads(body["manifest_json"])
    assert manifest["version"] == "0.4.2"
    sig = bytes.fromhex(body["manifest_sig_hex"])
    ca_fixture.signing_pubkey().verify(sig, body["manifest_json"].encode())


@pytest.mark.asyncio
async def test_upload_rejects_non_ci(sm, mock_admin_token, ca_fixture, tmp_path):
    """Upload without CI token returns 401/403."""
    files = {"binary": ("x", b"x")}
    data = {
        "version": "0.0.1",
        "channel": "stable",
        "os": "linux",
        "arch": "amd64",
    }

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    dist_dir = tmp_path / "agent-dist"
    with mock.patch.dict("os.environ", {"HL_CI_TOKEN": "", "HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                "/v1/agent-releases",
                files=files,
                data=data,
            )

    assert r.status_code in (401, 403, 503)


@pytest.mark.asyncio
async def test_list_releases(sm, mock_ci_token, ca_fixture, tmp_path):
    """List releases returns all releases."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Upload a release via DB directly
    async with sm() as session:
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="abc" * 21 + "def",
            size=1024,
            manifest_json=b"{}",
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get("/v1/agent-releases")

    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["version"] == "0.5.0"


@pytest.mark.asyncio
async def test_list_releases_filter_by_os(sm, ca_fixture, tmp_path):
    """List releases filters by OS."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Upload releases for different OSes
    async with sm() as session:
        for os_name in ["linux", "darwin"]:
            rel = AgentRelease(
                version="0.5.0",
                channel=ReleaseChannel.STABLE,
                os=os_name,
                arch="amd64",
                sha256="abc" * 21 + "def",
                size=1024,
                manifest_json=b"{}",
                manifest_sig=b"sig",
                status=ReleaseStatus.PUBLISHED,
                uploaded_by="test",
            )
            session.add(rel)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get("/v1/agent-releases?os=linux")

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["os"] == "linux"


@pytest.mark.asyncio
async def test_get_latest(sm, mock_ci_token, ca_fixture, tmp_path):
    """GET /latest returns newest published release."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Upload a release
    binary = b"X" * 256
    files = {"binary": ("hl-agent", binary, "application/octet-stream")}
    data = {
        "version": "0.5.0",
        "channel": "stable",
        "os": "linux",
        "arch": "amd64",
    }

    dist_dir = tmp_path / "agent-dist"
    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                "/v1/agent-releases",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {mock_ci_token}"},
            )
            assert r.status_code == 201

            # Must call get inside the env context
            r = await client.get("/v1/agent-releases/latest?os=linux&arch=amd64")
            body = r.json()
            assert body["version"] == "0.5.0"
            assert body["channel"] == "stable"


@pytest.mark.asyncio
async def test_get_latest_not_found(sm, ca_fixture, tmp_path):
    """GET /latest returns 404 when no published release exists."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get("/v1/agent-releases/latest?os=linux&arch=amd64")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_manifest(sm, ca_fixture, tmp_path):
    """GET /{rid}/manifest returns signed manifest."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a release
    async with sm() as session:
        manifest_json = b'{"version":"0.5.0"}'
        sig = ca_fixture.sign_release_manifest(manifest_json)
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="abc" * 21 + "def",
            size=1024,
            manifest_json=manifest_json,
            manifest_sig=sig,
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()
        rid = rel.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get(f"/v1/agent-releases/{rid}/manifest")

    assert r.status_code == 200
    body = r.json()
    assert "manifest_json" in body
    assert "manifest_sig_hex" in body
    assert json.loads(body["manifest_json"])["version"] == "0.5.0"


@pytest.mark.asyncio
async def test_get_manifest_yanked_404(sm, ca_fixture, tmp_path):
    """GET /{rid}/manifest returns 404 for yanked release."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a yanked release
    async with sm() as session:
        manifest_json = b'{"version":"0.5.0"}'
        sig = ca_fixture.sign_release_manifest(manifest_json)
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="abc" * 21 + "def",
            size=1024,
            manifest_json=manifest_json,
            manifest_sig=sig,
            status=ReleaseStatus.YANKED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()
        rid = rel.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get(f"/v1/agent-releases/{rid}/manifest")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_binary_requires_token(sm, ca_fixture, tmp_path):
    """GET /{rid}/binary requires download token."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a release
    async with sm() as session:
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="abc" * 21 + "def",
            size=256,
            manifest_json=b"{}",
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()
        rid = rel.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get(f"/v1/agent-releases/{rid}/binary")

    assert r.status_code in (401, 422)


@pytest.mark.asyncio
async def test_get_binary_with_valid_token(sm, ca_fixture, tmp_path):
    """GET /{rid}/binary with valid token returns binary."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create binary file
    binary_data = b"X" * 256
    dist_dir = tmp_path / "agent-dist"

    # Create a release
    async with sm() as session:
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256=hashlib.sha256(binary_data).hexdigest(),
            size=len(binary_data),
            manifest_json=b"{}",
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()
        rid = rel.id

    # Write binary file
    binary_path = dist_dir / "releases" / "0.5.0" / "linux-amd64"
    binary_path.mkdir(parents=True, exist_ok=True)
    (binary_path / "hl-agent").write_bytes(binary_data)

    # Mock the environment for the agent releases endpoint
    with mock.patch.dict("os.environ", {"HL_AGENT_DIST_DIR": str(dist_dir)}):
        # Generate token
        token = make_download_token(rid, "host-123")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get(f"/v1/agent-releases/{rid}/binary?token={token}")

    assert r.status_code == 200
    assert r.content == binary_data


@pytest.mark.asyncio
async def test_yank_release(sm, mock_admin_token, ca_fixture, tmp_path):
    """POST /{rid}/yank marks release as yanked."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a release
    async with sm() as session:
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="abc" * 21 + "def",
            size=1024,
            manifest_json=b"{}",
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()
        rid = rel.id

    with mock.patch("server.app.api.v1.agent_releases._release_dir"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                f"/v1/agent-releases/{rid}/yank",
                json={"reason": "security issue"},
                headers={"Authorization": "Bearer test-admin-token"},
            )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "yanked"
    assert body["yanked_reason"] == "security issue"


@pytest.mark.asyncio
async def test_yank_requires_admin(sm, ca_fixture, tmp_path):
    """POST /{rid}/yank requires admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm, ca=ca_fixture, tmp_path=tmp_path)

    # Create a release
    async with sm() as session:
        rel = AgentRelease(
            version="0.5.0",
            channel=ReleaseChannel.STABLE,
            os="linux",
            arch="amd64",
            sha256="abc" * 21 + "def",
            size=1024,
            manifest_json=b"{}",
            manifest_sig=b"sig",
            status=ReleaseStatus.PUBLISHED,
            uploaded_by="test",
        )
        session.add(rel)
        await session.commit()
        rid = rel.id

    with mock.patch("server.app.api.middleware.admin_auth.load_settings") as mock_load:
        from pydantic import SecretStr
        settings = mock.MagicMock()
        settings.admin_token = SecretStr("test-admin-token")
        mock_load.return_value = settings

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                f"/v1/agent-releases/{rid}/yank",
                json={"reason": "security issue"},
            )

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_make_download_token():
    """make_download_token creates valid JWT token."""
    import jwt

    # Create a token and decode it
    token = make_download_token("release-123", "host-456")

    # Decode - the secret should be derived from default settings
    # Use the same secret generation as the implementation
    claims = jwt.decode(
        token,
        "test-secret-key-change-in-prod",  # Default secret when admin_token is None
        algorithms=["HS256"],
    )
    assert claims["rid"] == "release-123"
    assert claims["hid"] == "host-456"
    assert "exp" in claims
