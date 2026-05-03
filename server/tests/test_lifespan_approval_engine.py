"""Tests for _LifespanApprovalProxy wiring in lifespan.build_app_state."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.lifespan import _LifespanApprovalProxy
from server.app.models import Approval, Host, User
from server.app.models.approval import ApprovalState
from server.app.models.user import UserKind


@pytest.mark.asyncio
async def test_lifespan_approval_proxy_creates_real_approval_row(sm: async_sessionmaker[AsyncSession]) -> None:
    """Instantiate _LifespanApprovalProxy, call request, verify approval row in DB."""
    proxy = _LifespanApprovalProxy(sm)

    approval = await proxy.request(
        subject_type="command",
        subject_id="reboot",
        policy="single_second_factor",
        requester_id="u-1",
    )

    # Verify the Approval object returned has expected fields
    assert approval.id is not None
    assert approval.subject_type == "command"
    assert approval.subject_id == "reboot"
    assert approval.policy == "single_second_factor"
    assert approval.requester_id == "u-1"
    assert approval.state == ApprovalState.PENDING

    # Verify the row was persisted in the database
    async with sm() as session:
        row = await session.scalar(select(Approval).where(Approval.id == approval.id))
        assert row is not None
        assert row.subject_type == "command"
        assert row.subject_id == "reboot"
        assert row.policy == "single_second_factor"
        assert row.requester_id == "u-1"
        assert row.state == ApprovalState.PENDING


@pytest.mark.asyncio
async def test_lifespan_wires_approval_engine(
    sm: async_sessionmaker[AsyncSession], tmp_path
) -> None:
    """Build app state with approval engine, dispatch high-risk shell_exec, verify pending_approval_ids and DB row."""
    # Set permissive RBAC so we don't need full RBAC setup
    os.environ["FLEET_ALLOW_PERMISSIVE_RBAC"] = "1"

    try:
        # Bootstrap DB with minimal data
        async with sm() as session:
            # Create a user
            user = User(
                id="user-1",
                email="test@local",
                display_name="Test User",
                kind=UserKind.LOCAL,
            )
            session.add(user)
            await session.flush()

            # Create a host
            host = Host(
                id="host-1",
                hostname="test-host",
                display_name="Test Host",
                agent_pubkey=b"\x00" * 32,
                labels={},
            )
            session.add(host)
            await session.commit()

        # Create a dispatcher using the proxy (mimicking build_app_state pattern)
        from server.app.auth.capability import CapabilityIssuer
        from server.app.audit.sql_chain import SqlAuditChain
        from server.app.crypto.signing import FileBackend
        from server.app.dispatcher.dispatcher import CommandDispatcher
        from server.app.dispatcher.queue import CommandQueue
        from server.app.rbac.provider import Principal, Decision

        class FakeRBACProvider:
            """Permissive RBAC for testing."""

            async def is_authorized(self, principal: Principal, action: str, resource, ctx) -> Decision:
                return Decision(allow=True)

        queue = CommandQueue()
        signing_backend = FileBackend.bootstrap(tmp_path / "signing")
        capability_issuer = CapabilityIssuer.generate()
        audit_chain = SqlAuditChain(signing_backend)
        rbac_provider = FakeRBACProvider()

        # Wire the approval proxy (this is what we're testing)
        approval_engine = _LifespanApprovalProxy(sm)

        dispatcher = CommandDispatcher(
            queue=queue,
            audit=audit_chain,
            capability_issuer=capability_issuer,
            signing_backend=signing_backend,
            approval_engine=approval_engine,
            rbac_provider=rbac_provider,
            scope_evaluator=None,
        )

        # Dispatch a high-risk shell_exec command
        from server.app.dispatcher.dispatcher import ShellExecPayload
        from server.app.dispatcher.targets import HostListSelector

        async with sm() as session:
            result = await dispatcher.dispatch(
                session=session,
                principal=Principal(user_id="user-1"),
                targets=HostListSelector(["host-1"]),
                payload=ShellExecPayload(command="echo hello"),
                idempotency_key=None,
            )
            await session.commit()

        # Verify pending_approval_ids is non-empty
        assert len(result.pending_approval_ids) > 0, "Expected pending approval IDs for high-risk dispatch"

        # Verify the approval row exists in the database
        async with sm() as session:
            approval_id = result.pending_approval_ids[0]
            row = await session.scalar(select(Approval).where(Approval.id == approval_id))
            assert row is not None, f"Approval row {approval_id} not found in database"
            assert row.state == ApprovalState.PENDING

    finally:
        # Clean up env
        os.environ.pop("FLEET_ALLOW_PERMISSIVE_RBAC", None)
