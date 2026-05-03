"""Tests for /v1/tasks API endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr
from sqlalchemy import select

from server.app.api.app import create_app
from server.app.models import TaskRun, Command
from server.app.models.command import CommandStatus
from server.app.models.task_run import TaskRunStatus
from server.app.settings.config import FleetSettings


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    """Set admin token in environment."""
    monkeypatch.setenv("FLEET_ADMIN_TOKEN", "test-tok")


@pytest.fixture
def auth():
    """Return admin auth headers."""
    return {"Authorization": "Bearer test-tok"}


@pytest.fixture
def mock_settings():
    """Return mocked settings with admin token."""
    return FleetSettings(admin_token=SecretStr("test-tok"))


@pytest.mark.asyncio
async def test_create_task_201(auth, sm, mock_settings):
    """POST /v1/tasks returns 201 with created task."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            assert r.status_code == 201
            d = r.json()
            assert d["kind"] == "shell_exec"
            assert d["payload"] == {"command": "echo hello"}
            assert d["target_selector"] == {"group_id": "g-1"}
            assert d["status"] == "pending"
            assert "id" in d
            assert "created_at" in d
            assert "updated_at" in d


@pytest.mark.asyncio
async def test_get_task_200(auth, sm, mock_settings):
    """GET /v1/tasks/{task_id} returns 200."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "reboot",
                "payload": {},
                "target_selector": {"host_id": "h-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Get task
            r2 = await c.get(f"/v1/tasks/{task_id}", headers=auth)
            assert r2.status_code == 200
            d = r2.json()
            assert d["id"] == task_id
            assert d["kind"] == "reboot"


@pytest.mark.asyncio
async def test_get_task_404(auth, sm, mock_settings):
    """GET /v1/tasks/{task_id} returns 404 for missing task."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/v1/tasks/nonexistent", headers=auth)
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks_200(auth, sm, mock_settings):
    """GET /v1/tasks returns 200 with list."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create two tasks
            for i in range(2):
                body = {
                    "kind": "shell_exec",
                    "payload": {"command": f"echo {i}"},
                    "target_selector": {"group_id": "g-1"},
                }
                await c.post("/v1/tasks", json=body, headers=auth)

            # List tasks
            r = await c.get("/v1/tasks", headers=auth)
            assert r.status_code == 200
            d = r.json()
            assert "items" in d
            assert len(d["items"]) == 2
            assert "next_cursor" in d


@pytest.mark.asyncio
async def test_patch_task_200(auth, sm, mock_settings):
    """PATCH /v1/tasks/{task_id} returns 200."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Patch task
            patch_body = {
                "payload": {"command": "echo world"},
            }
            r2 = await c.patch(f"/v1/tasks/{task_id}", json=patch_body, headers=auth)
            assert r2.status_code == 200
            d = r2.json()
            assert d["payload"] == {"command": "echo world"}


@pytest.mark.asyncio
async def test_patch_task_404(auth, sm, mock_settings):
    """PATCH /v1/tasks/{task_id} returns 404 for missing task."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            patch_body = {"payload": {}}
            r = await c.patch("/v1/tasks/nonexistent", json=patch_body, headers=auth)
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_204(auth, sm, mock_settings):
    """DELETE /v1/tasks/{task_id} returns 204."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Delete task
            r2 = await c.delete(f"/v1/tasks/{task_id}", headers=auth)
            assert r2.status_code == 204


@pytest.mark.asyncio
async def test_delete_task_404(auth, sm, mock_settings):
    """DELETE /v1/tasks/{task_id} returns 404 for missing task."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.delete("/v1/tasks/nonexistent", headers=auth)
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_with_running_taskruns_409(auth, sm, mock_settings):
    """DELETE /v1/tasks/{task_id} returns 409 if task has running TaskRuns."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Manually add a running TaskRun
            async with sm() as session:
                tr = TaskRun(
                    id=str(uuid4()),
                    task_id=task_id,
                    host_id="h-1",
                    status=TaskRunStatus.RUNNING,
                )
                session.add(tr)
                await session.commit()

            # Try to delete - should return 409
            r2 = await c.delete(f"/v1/tasks/{task_id}", headers=auth)
            assert r2.status_code == 409


@pytest.mark.asyncio
async def test_dispatch_task_503_no_dispatcher(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/dispatch returns 503 when dispatcher not available."""
    app = create_app()
    app.state.sessionmaker = sm
    # Don't set dispatcher on app.state
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Try to dispatch without dispatcher
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r2 = await c.post(
                f"/v1/tasks/{task_id}/dispatch",
                json={},
                headers=headers,
            )
            assert r2.status_code == 503


@pytest.mark.asyncio
async def test_dispatch_task_missing_acting_principal_400(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/dispatch without X-Acting-Principal returns 400."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Try to dispatch without X-Acting-Principal
            r2 = await c.post(
                f"/v1/tasks/{task_id}/dispatch",
                json={},
                headers=auth,
            )
            assert r2.status_code == 400
            assert "acting_principal_required" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_task_200(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/cancel returns 200."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Create a TaskRun and IN_FLIGHT Command
            async with sm() as session:
                tr = TaskRun(
                    id=str(uuid4()),
                    task_id=task_id,
                    host_id="h-1",
                    status=TaskRunStatus.RUNNING,
                )
                session.add(tr)
                await session.commit()
                # Refresh to get id
                await session.refresh(tr)

                cmd = Command(
                    id=str(uuid4()),
                    task_run_id=tr.id,
                    host_id="h-1",
                    sequence=1,
                    envelope_bytes=b"test",
                    risk="low",
                    issued_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    status=CommandStatus.IN_FLIGHT,
                )
                session.add(cmd)
                await session.commit()

            # Cancel the task
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r2 = await c.post(
                f"/v1/tasks/{task_id}/cancel",
                json={},
                headers=headers,
            )
            assert r2.status_code == 200

            # Verify command was marked CANCELLED
            async with sm() as session:
                cmd_row = await session.scalar(select(Command))
                assert cmd_row.status == CommandStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_task_missing_acting_principal_400(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/cancel without X-Acting-Principal returns 400."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Try to cancel without X-Acting-Principal
            r2 = await c.post(
                f"/v1/tasks/{task_id}/cancel",
                json={},
                headers=auth,
            )
            assert r2.status_code == 400
            assert "acting_principal_required" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_results_task_200(auth, sm, mock_settings):
    """GET /v1/tasks/{task_id}/results returns 200 with aggregated results."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Create TaskRun and Command
            async with sm() as session:
                tr = TaskRun(
                    id=str(uuid4()),
                    task_id=task_id,
                    host_id="h-1",
                    status=TaskRunStatus.SUCCEEDED,
                )
                session.add(tr)
                await session.commit()
                await session.refresh(tr)

                cmd = Command(
                    id=str(uuid4()),
                    task_run_id=tr.id,
                    host_id="h-1",
                    sequence=1,
                    envelope_bytes=b"test",
                    risk="low",
                    issued_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    status=CommandStatus.SUCCEEDED,
                )
                session.add(cmd)
                await session.commit()

            # Get results
            r2 = await c.get(f"/v1/tasks/{task_id}/results", headers=auth)
            assert r2.status_code == 200
            d = r2.json()
            assert "results" in d
            assert len(d["results"]) == 1
            assert d["results"][0]["host_id"] == "h-1"
            assert d["results"][0]["status"] == "succeeded"
            assert d["results"][0]["last_command_id"] == cmd.id


@pytest.mark.asyncio
async def test_tasks_require_admin_401(sm):
    """All /v1/tasks endpoints require admin auth."""
    app = create_app()
    app.state.sessionmaker = sm
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        # Try without auth
        r = await c.get("/v1/tasks")
        assert r.status_code == 401

        r = await c.post("/v1/tasks", json={})
        assert r.status_code == 401
