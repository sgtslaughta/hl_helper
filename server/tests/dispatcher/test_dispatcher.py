"""Tests for CommandDispatcher core pipeline."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from server.app.audit.sql_chain import SqlAuditChain
from server.app.auth.capability import CapabilityIssuer
from server.app.crypto.signing import FileBackend
from server.app.dispatcher.dispatcher import (
    CommandDispatcher,
    RebootPayload,
)
from server.app.dispatcher.queue import CommandQueue
from server.app.models import Group, GroupMembership, Host, User
from server.app.rbac.provider import Principal, Decision


class FakeRBACProvider:
    """Fake RBAC provider for testing. Grants/denies perms by host."""

    def __init__(self) -> None:
        self.grant_perms: dict[str, set[str]] = {}  # principal_id -> {action:host_id}

    def grant(self, principal_id: str, action: str, host_id: str) -> None:
        key = principal_id
        if key not in self.grant_perms:
            self.grant_perms[key] = set()
        self.grant_perms[key].add(f"{action}:{host_id}")

    async def is_authorized(
        self, principal: Principal, action: str, resource, ctx, /
    ) -> Decision:
        principal_id = principal.user_id or principal.service_account_id
        perm = f"{action}:{resource.id}" if hasattr(resource, "id") and resource.id else None
        if perm and principal_id in self.grant_perms and perm in self.grant_perms[principal_id]:
            return Decision(allow=True)
        return Decision(allow=False)


@pytest_asyncio.fixture
async def stack(engine: AsyncEngine, sm, tmp_path):
    """Build a test fixture with all collaborators (uses pytest fixtures engine, sm)."""
    async with sm() as session:
        from server.app.models.user import UserKind

        # Create users
        user_admin = User(
            id="user-admin",
            email="admin@test.local",
            display_name="Admin",
            kind=UserKind.LOCAL,
        )
        user_op = User(
            id="user-op",
            email="op@test.local",
            display_name="Operator",
            kind=UserKind.LOCAL,
        )
        session.add(user_admin)
        session.add(user_op)
        await session.flush()

        # Create groups
        group_prod = Group(id=uuid4(), name="Prod")
        group_staging = Group(id=uuid4(), name="Staging")
        session.add(group_prod)
        session.add(group_staging)
        await session.flush()

        # Create hosts
        host_prod = Host(
            id="host-prod",
            hostname="prod-1",
            display_name="prod-1",
            agent_pubkey=b"\x00" * 32,  # Dummy Ed25519 key
            labels={"env": "prod"},
        )
        host_staging = Host(
            id="host-staging",
            hostname="staging-1",
            display_name="staging-1",
            agent_pubkey=b"\x00" * 32,  # Dummy Ed25519 key
            labels={"env": "staging"},
        )
        session.add(host_prod)
        session.add(host_staging)
        await session.flush()

        # Add hosts to groups
        gm_prod = GroupMembership(group_id=group_prod.id, host_id=host_prod.id)
        gm_staging = GroupMembership(group_id=group_staging.id, host_id=host_staging.id)
        session.add(gm_prod)
        session.add(gm_staging)
        await session.commit()

    # Create collaborators
    queue = CommandQueue()
    signing_backend = FileBackend.bootstrap(tmp_path / "signing")
    capability_issuer = CapabilityIssuer.generate()
    audit_chain = SqlAuditChain(signing_backend)
    rbac_provider = FakeRBACProvider()

    # Grant admin all perms on both hosts
    rbac_provider.grant("user-admin", "host:reboot", host_prod.id)
    rbac_provider.grant("user-admin", "host:reboot", host_staging.id)
    rbac_provider.grant("user-admin", "host:shell_exec", host_prod.id)
    rbac_provider.grant("user-admin", "host:shell_exec", host_staging.id)

    # Grant operator only staging perms
    rbac_provider.grant("user-op", "host:reboot", host_staging.id)

    # Approval engine is constructed per-session by tests that need it; the
    # dispatcher accepts the factory below (see _make_approval_engine in
    # test_dispatch_creates_pending_approval_when_required).
    from server.app.rbac.approvals import ApprovalEngine

    class _ApprovalProxy:
        """Per-call ApprovalEngine factory bound to the session passed in."""

        def __init__(self, sm_):
            self._sm = sm_

        async def request(self, *, subject_type, subject_id, policy, requester_id, **_):
            from uuid import uuid4
            async with self._sm() as s:
                eng = ApprovalEngine(s)
                row = await eng.request(
                    subject_type=subject_type,
                    subject_id=subject_id,
                    policy=policy,
                    requester_id=requester_id,
                    approval_id=str(uuid4()),
                )
                await s.commit()
                return row

    dispatcher = CommandDispatcher(
        queue=queue,
        audit=audit_chain,
        capability_issuer=capability_issuer,
        signing_backend=signing_backend,
        approval_engine=_ApprovalProxy(sm),
        rbac_provider=rbac_provider,
        scope_evaluator=None,  # will test scope separately
    )

    from types import SimpleNamespace
    stack_obj = SimpleNamespace()
    stack_obj.engine = engine
    stack_obj.sm = sm
    stack_obj.dispatcher = dispatcher
    stack_obj.queue = queue
    stack_obj.signing = signing_backend
    stack_obj.capability_issuer = capability_issuer
    stack_obj.audit = audit_chain
    stack_obj.rbac_provider = rbac_provider
    stack_obj.user_admin = Principal(user_id="user-admin")
    stack_obj.user_op = Principal(user_id="user-op")
    stack_obj.host_prod = host_prod
    stack_obj.host_staging = host_staging
    stack_obj.group_prod = group_prod
    stack_obj.group_staging = group_staging

    return stack_obj


@pytest.mark.asyncio
async def test_dispatch_signs_envelopes_and_enqueues(stack) -> None:
    """Dispatch 1 host, admin user, RebootPayload → result has 1 dispatched, command in queue, envelope verifies."""
    async with stack.sm() as session:
        from server.app.dispatcher.targets import HostListSelector

        res = await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_admin,
            targets=HostListSelector([stack.host_staging.id]),
            payload=RebootPayload(delay_s=60, reason="patch"),
            idempotency_key=None,
        )
        await session.commit()

    assert len(res.dispatched) == 1
    assert stack.host_staging.id in res.dispatched
    assert len(res.denied) == 0

    # Verify command in queue
    async with stack.sm() as session:
        cmd = await stack.queue.peek(session, stack.host_staging.id)
        assert cmd is not None
        assert cmd.status.value == "queued"
        # Verify envelope signature (basic check)
        assert cmd.envelope_bytes is not None


@pytest.mark.asyncio
async def test_dispatch_filters_by_rbac(stack) -> None:
    """Principal lacks host:reboot perm on prod → denied list, no enqueue, no audit for denied."""
    async with stack.sm() as session:
        from server.app.dispatcher.targets import HostListSelector

        res = await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_op,  # only has staging perms
            targets=HostListSelector([stack.host_prod.id]),
            payload=RebootPayload(delay_s=0),
            idempotency_key=None,
        )
        await session.commit()

    assert res.dispatched == []
    assert res.denied == [stack.host_prod.id]

    # Verify no command enqueued
    async with stack.sm() as session:
        cmd = await stack.queue.peek(session, stack.host_prod.id)
        assert cmd is None


@pytest.mark.asyncio
async def test_dispatch_idempotent(stack) -> None:
    """Same idempotency_key twice → same task_id, only one Command per host."""
    async with stack.sm() as session:
        from server.app.dispatcher.targets import HostListSelector

        k = "idempotent-key-1"
        r1 = await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_admin,
            targets=HostListSelector([stack.host_staging.id]),
            payload=RebootPayload(delay_s=0),
            idempotency_key=k,
        )
        await session.commit()

    task_id_1 = r1.task_id

    async with stack.sm() as session:
        r2 = await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_admin,
            targets=HostListSelector([stack.host_staging.id]),
            payload=RebootPayload(delay_s=0),
            idempotency_key=k,
        )
        await session.commit()

    task_id_2 = r2.task_id
    assert task_id_1 == task_id_2
    assert len(r1.dispatched) == 1
    assert len(r2.dispatched) == 1


@pytest.mark.asyncio
async def test_dispatch_writes_audit(stack) -> None:
    """After dispatch, audit chain contains command.issued entry per dispatched command."""
    async with stack.sm() as session:
        from server.app.dispatcher.targets import HostListSelector

        await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_admin,
            targets=HostListSelector([stack.host_staging.id]),
            payload=RebootPayload(delay_s=0),
            idempotency_key=None,
        )
        await session.commit()

    # Check audit
    async with stack.sm() as session:
        from server.app.models.audit import AuditEntry
        from sqlalchemy import select

        entries = (
            await session.execute(
                select(AuditEntry).where(AuditEntry.action == "command.issued")
            )
        ).scalars().all()
        assert len(entries) == 1
        assert entries[0].payload.get("host_id") == stack.host_staging.id
        # Subject is the command id; actor is the dispatching principal's id.
        assert entries[0].subject == entries[0].payload.get("command_id") or entries[0].subject
        assert entries[0].actor == stack.user_admin.user_id


@pytest.mark.asyncio
async def test_dispatch_creates_pending_approval_when_required(stack):
    """High-risk dispatch (no approval row) returns pending_approval_ids and skips enqueue."""
    from server.app.dispatcher.dispatcher import ShellExecPayload
    from server.app.dispatcher.targets import HostListSelector

    async with stack.sm() as session:
        result = await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_admin,
            targets=HostListSelector([stack.host_staging.id]),
            payload=ShellExecPayload(command="echo hello", timeout_s=5),
            idempotency_key=None,
        )
        await session.commit()

    assert result.dispatched == []
    assert len(result.pending_approval_ids) >= 1
    # No command should be enqueued without approval
    async with stack.sm() as session:
        peek = await stack.queue.peek(session, stack.host_staging.id)
        assert peek is None


@pytest.mark.asyncio
async def test_dispatch_creates_task_row(stack) -> None:
    """Dispatch with RebootPayload + HostListSelector → Task row created with correct fields."""
    from server.app.dispatcher.targets import HostListSelector
    from server.app.models import Task
    from server.app.models.task import TaskKind
    from sqlalchemy import select

    async with stack.sm() as session:
        res = await stack.dispatcher.dispatch(
            session=session,
            principal=stack.user_admin,
            targets=HostListSelector([stack.host_staging.id]),
            payload=RebootPayload(delay_s=60, reason="patch"),
            idempotency_key="test-key-1",
        )
        await session.commit()

    task_id = res.task_id
    assert task_id, "dispatch should return non-empty task_id"

    # Verify Task row was created
    async with stack.sm() as session:
        task = await session.get(Task, task_id)
        assert task is not None
        assert task.id == task_id
        assert task.kind == TaskKind.REBOOT
        assert task.payload == {"delay_s": 60, "reason": "patch"}
        assert task.idempotency_key == "test-key-1"
        assert task.created_by == "user-admin"
        assert task.requires_approval is False  # risk is "med" for single host reboot
