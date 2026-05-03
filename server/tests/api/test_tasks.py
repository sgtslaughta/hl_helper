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
from server.tests._helpers.app_state import make_test_app_state


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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
async def test_dispatch_task_invokes_dispatcher(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/dispatch invokes dispatcher with correct params."""
    from server.app.dispatcher.dispatcher import DispatchResult

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    # Create a mock dispatcher
    mock_dispatcher = mock.AsyncMock()
    mock_dispatcher.dispatch = mock.AsyncMock(
        return_value=DispatchResult(
            task_id="task-123",
            dispatched=["h-1", "h-2"],
            denied=[],
            pending_approval_ids=[],
        )
    )

    # Attach mock to app.state as api_dispatcher (preferred) or dispatcher
    state = mock.MagicMock()
    state.api_dispatcher = mock_dispatcher
    state.sessionmaker = sm
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task with reboot payload
            body = {
                "kind": "reboot",
                "payload": {"delay_s": 5, "reason": "testing"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Dispatch the task
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r2 = await c.post(
                f"/v1/tasks/{task_id}/dispatch",
                json={},
                headers=headers,
            )
            assert r2.status_code == 200
            d = r2.json()
            assert d["task_id"] == "task-123"
            assert d["dispatched"] == 2
            assert d["denied"] == 0
            assert d["pending_approval_ids"] == []

            # Verify dispatcher was called
            assert mock_dispatcher.dispatch.called


@pytest.mark.asyncio
async def test_dispatch_task_404_unknown_task(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/dispatch returns 404 for nonexistent task."""
    from server.app.dispatcher.dispatcher import DispatchResult

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    # Create a mock dispatcher
    mock_dispatcher = mock.AsyncMock()
    mock_dispatcher.dispatch = mock.AsyncMock(
        return_value=DispatchResult(
            task_id="task-123",
            dispatched=["h-1"],
            denied=[],
            pending_approval_ids=[],
        )
    )

    state = mock.MagicMock()
    state.api_dispatcher = mock_dispatcher
    state.sessionmaker = sm
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Try to dispatch nonexistent task
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post(
                "/v1/tasks/nonexistent-task-id/dispatch",
                json={},
                headers=headers,
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_dispatch_task_with_target_override(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/dispatch with targets override."""
    from server.app.dispatcher.dispatcher import DispatchResult

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    # Create a mock dispatcher
    mock_dispatcher = mock.AsyncMock()
    mock_dispatcher.dispatch = mock.AsyncMock(
        return_value=DispatchResult(
            task_id="task-123",
            dispatched=["h-override"],
            denied=[],
            pending_approval_ids=[],
        )
    )

    state = mock.MagicMock()
    state.api_dispatcher = mock_dispatcher
    state.sessionmaker = sm
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task with group selector
            body = {
                "kind": "shell_exec",
                "payload": {"command": "echo hello"},
                "target_selector": {"group_id": "g-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            task_id = r.json()["id"]

            # Dispatch with host override
            headers = {**auth, "X-Acting-Principal": "u-1"}
            dispatch_body = {
                "targets": {"host_id": "h-override"}
            }
            r2 = await c.post(
                f"/v1/tasks/{task_id}/dispatch",
                json=dispatch_body,
                headers=headers,
            )
            assert r2.status_code == 200
            d = r2.json()
            assert d["dispatched"] == 1


@pytest.mark.asyncio
async def test_dispatch_task_503_no_dispatcher(auth, sm, mock_settings):
    """POST /v1/tasks/{task_id}/dispatch returns 503 when dispatcher not available."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    # Explicitly clear api_dispatcher so the route hits the 503 path.
    app.state.app_state.api_dispatcher = None  # type: ignore[assignment]
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
    app.state.app_state = make_test_app_state(sessionmaker=sm)
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
async def test_dispatch_task_real_dispatcher_end_to_end(auth, sm, mock_settings, tmp_path):
    """POST /v1/tasks/{id}/dispatch with real CommandDispatcher + Host in DB."""
    from server.app.auth.capability import CapabilityIssuer
    from server.app.crypto.signing import FileBackend
    from server.app.dispatcher.dispatcher import CommandDispatcher
    from server.app.dispatcher.queue import CommandQueue
    from server.app.audit.sql_chain import SqlAuditChain
    from server.app.rbac.provider import Decision
    from server.app.models import Host
    from sqlalchemy import select

    # Permissive RBAC stub — always returns Decision.ALLOW
    class PermissiveRBAC:
        async def is_authorized(self, principal, action, resource, ctx):
            return Decision(allow=True)

    # Create Host in DB
    async with sm() as session:
        host = Host(
            id="h-1",
            hostname="test-host",
            display_name="test-host",
            agent_pubkey=b"\x00" * 32,  # Dummy Ed25519 key
            labels={},
        )
        session.add(host)
        await session.commit()

    # Build real dispatcher components
    queue = CommandQueue()
    signing_backend = FileBackend.bootstrap(tmp_path / "signing")
    capability_issuer = CapabilityIssuer.generate()
    audit_chain = SqlAuditChain(signing_backend)
    rbac_provider = PermissiveRBAC()

    dispatcher = CommandDispatcher(
        queue=queue,
        audit=audit_chain,
        capability_issuer=capability_issuer,
        signing_backend=signing_backend,
        approval_engine=None,  # Not needed for low-risk reboot
        rbac_provider=rbac_provider,
        scope_evaluator=None,
    )

    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)

    # Inject dispatcher into app.state.app_state
    state = mock.MagicMock()
    state.api_dispatcher = dispatcher
    state.sessionmaker = sm
    app.state.app_state = state

    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create task with reboot payload
            body = {
                "kind": "reboot",
                "payload": {"delay_s": 5, "reason": "testing"},
                "target_selector": {"host_id": "h-1"},
            }
            r = await c.post("/v1/tasks", json=body, headers=auth)
            assert r.status_code == 201
            task_id = r.json()["id"]

            # Dispatch the task
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r2 = await c.post(
                f"/v1/tasks/{task_id}/dispatch",
                json={},
                headers=headers,
            )
            assert r2.status_code == 200
            d = r2.json()
            assert d["dispatched"] == 1
            assert d["denied"] == 0
            assert d["pending_approval_ids"] == []

            # Verify Command row in DB
            async with sm() as session:
                cmds = (await session.execute(select(Command))).scalars().all()
                assert len(cmds) == 1
                cmd = cmds[0]
                assert cmd.host_id == "h-1"
                assert cmd.status == CommandStatus.QUEUED


@pytest.mark.asyncio
async def test_tasks_require_admin_401(sm):
    """All /v1/tasks endpoints require admin auth."""
    app = create_app()
    app.state.app_state = make_test_app_state(sessionmaker=sm)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        # Try without auth
        r = await c.get("/v1/tasks")
        assert r.status_code == 401

        r = await c.post("/v1/tasks", json={})
        assert r.status_code == 401
