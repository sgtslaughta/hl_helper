"""Tests for /v1/approvals API endpoint."""

from __future__ import annotations

from unittest import mock

import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr

from server.app.api.app import create_app
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
async def test_list_approvals_admin_gated_401():
    """GET /v1/approvals without auth returns 401."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/approvals")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_approval_missing_header_400(auth, sm, mock_settings):
    """POST /v1/approvals without X-Acting-Principal header returns 400."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers=auth,
            )
            assert r.status_code == 400
            assert "acting_principal_required" in r.json()["detail"]


@pytest.mark.asyncio
async def test_decide_approval_missing_header_400(auth, sm, mock_settings):
    """POST /v1/approvals/{id}/decisions without X-Acting-Principal header returns 400."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve"},
                headers=auth,
            )
            assert r2.status_code == 400
            assert "acting_principal_required" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_create_approval_201(auth, sm, mock_settings):
    """POST /v1/approvals returns 201 with created approval."""
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
                "subject_type": "command",
                "subject_id": "c-1",
                "policy": "two_person",
            }
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post("/v1/approvals", json=body, headers=headers)
            assert r.status_code == 201
            d = r.json()
            assert d["state"] == "pending"
            assert d["subject_id"] == "c-1"
            assert d["requester_id"] == "u-1"


@pytest.mark.asyncio
async def test_two_person_same_principal_rejected_200(auth, sm, mock_settings):
    """Two-person approval with same principal rejected; returns 200 with decision."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-1"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-2",
                    "policy": "two_person",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve"},
                headers=headers,
            )
            assert r2.status_code == 200
            assert r2.json()["rejected_reason"] == "same_principal"
            assert r2.json()["approved"] is False


@pytest.mark.asyncio
async def test_two_person_first_approve_goes_to_pending_second(auth, sm, mock_settings):
    """Two-person approval first approve transitions to pending_second."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-1",
                    "policy": "two_person",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve"},
                headers=headers_d,
            )
            assert r2.json()["approved"] is False
            assert r2.json()["state"] == "pending_second"


@pytest.mark.asyncio
async def test_two_person_second_approve_different_principal_approves(auth, sm, mock_settings):
    """Two-person approval second approve from different principal approves."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-2",
                    "policy": "two_person",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            # First approve
            headers_d1 = {**auth, "X-Acting-Principal": "u-d1"}
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve"},
                headers=headers_d1,
            )
            assert r2.json()["state"] == "pending_second"
            # Second approve from different principal
            headers_d2 = {**auth, "X-Acting-Principal": "u-d2"}
            r3 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve"},
                headers=headers_d2,
            )
            assert r3.json()["approved"] is True
            assert r3.json()["state"] == "approved"


@pytest.mark.asyncio
async def test_decide_unknown_id_404(auth, sm, mock_settings):
    """POST /v1/approvals/{id}/decisions with unknown id returns 404."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-d"}
            r = await c.post(
                "/v1/approvals/does-not-exist/decisions",
                json={"decision": "approve"},
                headers=headers,
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_filter_by_state(auth, sm, mock_settings):
    """GET /v1/approvals?state=approved filters by state."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create two pending approvals
            headers_r = {**auth, "X-Acting-Principal": "u-r"}
            for i in range(2):
                await c.post(
                    "/v1/approvals",
                    json={
                        "subject_type": "task",
                        "subject_id": f"t-{i}",
                        "policy": "single",
                    },
                    headers=headers_r,
                )
            # Approve only the first
            approvals = (await c.get("/v1/approvals", headers=auth)).json()["items"]
            first_id = approvals[0]["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            await c.post(
                f"/v1/approvals/{first_id}/decisions",
                json={"decision": "approve"},
                headers=headers_d,
            )
            r = await c.get("/v1/approvals?state=approved", headers=auth)
            states = {a["state"] for a in r.json()["items"]}
            assert states == {"approved"}


@pytest.mark.asyncio
async def test_ttl_minutes_clamps_to_max(auth, sm, mock_settings):
    """ttl_minutes > 1440 returns 422."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-x",
                    "policy": "single",
                    "ttl_minutes": 99999,
                },
                headers=headers,
            )
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_ttl_minutes_minimum_clamps(auth, sm, mock_settings):
    """ttl_minutes <= 0 returns 422."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-y",
                    "policy": "single",
                    "ttl_minutes": 0,
                },
                headers=headers,
            )
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_single_second_factor_pending_without_mfa(auth, sm, mock_settings):
    """POST single_sf approval; decide without mfa_proof → 200 with state=pending, rejected_reason=mfa_required."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-sf-1",
                    "policy": "single_second_factor",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve"},
                headers=headers_d,
            )
            assert r2.status_code == 200
            assert r2.json()["state"] == "pending"
            assert r2.json()["rejected_reason"] == "mfa_required"


@pytest.mark.asyncio
async def test_single_second_factor_approves_with_mfa(auth, sm, mock_settings):
    """POST single_sf approval; decide with mfa_proof → 200 with state=approved."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-sf-2",
                    "policy": "single_second_factor",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve", "mfa_proof": "totp:123456"},
                headers=headers_d,
            )
            assert r2.status_code == 200
            assert r2.json()["state"] == "approved"
            assert r2.json()["approved"] is True


@pytest.mark.asyncio
async def test_filter_by_subject_type(auth, sm, mock_settings):
    """GET /v1/approvals?subject_type=command filters correctly."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create two approvals with different subject_type
            headers = {**auth, "X-Acting-Principal": "u-r"}
            await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-1",
                    "policy": "single",
                },
                headers=headers,
            )
            await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "task",
                    "subject_id": "t-1",
                    "policy": "single",
                },
                headers=headers,
            )
            r = await c.get("/v1/approvals?subject_type=command", headers=auth)
            items = r.json()["items"]
            assert len(items) == 1
            assert items[0]["subject_type"] == "command"


@pytest.mark.asyncio
async def test_mfa_proof_redacted_in_list(auth, sm, mock_settings):
    """POST single_sf approval, decide+approve with mfa_proof; GET /v1/approvals; assert mfa_proof NOT in response."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-sf-redact",
                    "policy": "single_second_factor",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve", "mfa_proof": "totp:secret123"},
                headers=headers_d,
            )
            r2 = await c.get("/v1/approvals", headers=auth)
            items = r2.json()["items"]
            assert len(items) == 1
            assert "mfa_proof" not in items[0]


@pytest.mark.asyncio
async def test_mfa_proof_not_in_single_get(auth, sm, mock_settings):
    """POST single_sf approval, approve with mfa_proof; GET /v1/approvals/{id}; assert mfa_proof NOT in response."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-sf-single",
                    "policy": "single_second_factor",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "approve", "mfa_proof": "totp:single123"},
                headers=headers_d,
            )
            r2 = await c.get(f"/v1/approvals/{aid}", headers=auth)
            assert "mfa_proof" not in r2.json()


@pytest.mark.asyncio
async def test_get_single_approval_404(auth, sm, mock_settings):
    """GET /v1/approvals/{id} with unknown id returns 404."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/v1/approvals/does-not-exist", headers=auth)
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_pagination_returns_next_cursor(auth, sm, mock_settings):
    """POST 3 approvals with limit=2; verify next_cursor present."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            # Create 3 approvals
            headers = {**auth, "X-Acting-Principal": "u-r"}
            for i in range(3):
                await c.post(
                    "/v1/approvals",
                    json={
                        "subject_type": "task",
                        "subject_id": f"t-p-{i}",
                        "policy": "single",
                    },
                    headers=headers,
                )
            # Get first page with limit=2
            r = await c.get("/v1/approvals?limit=2", headers=auth)
            data = r.json()
            assert len(data["items"]) == 2
            assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_reject_decision_records_reason(auth, sm, mock_settings):
    """POST approval + decide reject with reason; verify reason stored."""
    app = create_app()
    app.state.sessionmaker = sm
    with mock.patch(
        "server.app.api.middleware.admin_auth.load_settings",
        return_value=mock_settings,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            headers = {**auth, "X-Acting-Principal": "u-r"}
            r = await c.post(
                "/v1/approvals",
                json={
                    "subject_type": "command",
                    "subject_id": "c-reject-reason",
                    "policy": "single",
                },
                headers=headers,
            )
            aid = r.json()["id"]
            headers_d = {**auth, "X-Acting-Principal": "u-d"}
            r2 = await c.post(
                f"/v1/approvals/{aid}/decisions",
                json={"decision": "reject", "reason": "security concern"},
                headers=headers_d,
            )
            assert r2.status_code == 200
            assert r2.json()["rejected_reason"] == "security concern"
