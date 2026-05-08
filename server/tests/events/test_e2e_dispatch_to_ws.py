"""End-to-end tests: dispatcher + audit wired to Bus."""

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
    ShellExecPayload,
)
from server.app.dispatcher.queue import CommandQueue
from server.app.events.bus import Bus
from server.app.models import Group, GroupMembership, Host, User
from server.app.rbac.provider import Principal, Decision


class FakeRBACProvider:
    """Fake RBAC provider for testing."""

    def __init__(self) -> None:
        self.grant_perms: dict[str, set[str]] = {}

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
async def stack_with_bus(engine: AsyncEngine, sm, tmp_path):
    """Build test fixture with Bus wired to dispatcher and audit chain."""
    async with sm() as session:
        from server.app.models.user import UserKind

        # Create users
        user_admin = User(
            id="user-admin",
            email="admin@test.local",
            display_name="Admin",
            kind=UserKind.LOCAL,
        )
        session.add(user_admin)
        await session.flush()

        # Create groups and hosts
        group_prod = Group(id=uuid4(), name="Prod")
        session.add(group_prod)
        await session.flush()

        host_prod = Host(
            id="host-prod",
            hostname="prod-1",
            display_name="prod-1",
            agent_pubkey=b"\x00" * 32,
            labels={"env": "prod"},
        )
        session.add(host_prod)
        await session.flush()

        gm_prod = GroupMembership(group_id=group_prod.id, host_id=host_prod.id)
        session.add(gm_prod)
        await session.commit()

    # Create collaborators with Bus
    bus = Bus()
    queue = CommandQueue()
    signing_backend = FileBackend.bootstrap(tmp_path / "signing")
    capability_issuer = CapabilityIssuer.generate()
    audit_chain = SqlAuditChain(signing_backend, event_bus=bus)
    rbac_provider = FakeRBACProvider()

    # Grant admin all perms (dispatcher maps shell_exec -> host:exec)
    rbac_provider.grant("user-admin", "host:reboot", host_prod.id)
    rbac_provider.grant("user-admin", "host:exec", host_prod.id)

    # Approval engine stub
    from server.app.rbac.approvals import ApprovalEngine

    class _ApprovalProxy:
        def __init__(self, sm_):
            self._sm = sm_

        async def request(self, *, subject_type, subject_id, policy, requester_id, **_):
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
        scope_evaluator=None,
        event_bus=bus,
    )

    class Stack:
        pass

    stack_obj = Stack()
    stack_obj.engine = engine
    stack_obj.sm = sm
    stack_obj.bus = bus
    stack_obj.dispatcher = dispatcher
    stack_obj.queue = queue
    stack_obj.signing = signing_backend
    stack_obj.audit = audit_chain
    stack_obj.rbac_provider = rbac_provider
    stack_obj.user_admin = Principal(user_id="user-admin")
    stack_obj.host_prod = host_prod
    stack_obj.group_prod = group_prod

    return stack_obj


@pytest.mark.asyncio
async def test_dispatch_low_risk_publishes_command_issued_event(stack_with_bus) -> None:
    """Dispatch low-risk reboot → bus subscriber receives command.issued on 'commands' channel."""
    from server.app.dispatcher.targets import HostListSelector

    # Subscribe to 'commands' channel
    commands_sub = stack_with_bus.bus.subscribe("commands")
    commands_events = []

    async def collect_commands():
        async for event in commands_sub:
            commands_events.append(event)
            if len(commands_events) >= 1:
                break

    import asyncio

    collect_task = asyncio.create_task(collect_commands())
    await asyncio.sleep(0.01)  # Let subscriber start

    # Dispatch low-risk reboot
    async with stack_with_bus.sm() as session:
        await stack_with_bus.dispatcher.dispatch(
            session=session,
            principal=stack_with_bus.user_admin,
            targets=HostListSelector([stack_with_bus.host_prod.id]),
            payload=RebootPayload(delay_s=60, reason="patch"),
            idempotency_key=None,
        )
        await session.commit()

    # Wait for event
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Verify event
    assert len(commands_events) >= 1
    event = commands_events[0]
    assert event.channel == "commands"
    assert event.payload["event"] == "command.issued"
    assert event.payload["command_id"]
    assert event.payload["host_id"] == stack_with_bus.host_prod.id
    # task_run_id is the run id; res.task_id is the parent Task id — different UUIDs.
    assert event.payload["task_run_id"]
    assert event.payload["risk"] == "low" or event.payload["risk"] == "med"
    assert event.payload["payload_kind"] == "reboot"
    assert event.payload["actor"] == "user-admin"


@pytest.mark.asyncio
async def test_dispatch_high_risk_publishes_pending_approval_event(stack_with_bus) -> None:
    """Dispatch high-risk shell_exec (no approval) → bus receives command.pending_approval."""
    from server.app.dispatcher.targets import HostListSelector

    # Subscribe to 'commands' channel
    commands_sub = stack_with_bus.bus.subscribe("commands")
    commands_events = []

    async def collect_commands():
        async for event in commands_sub:
            commands_events.append(event)
            if len(commands_events) >= 1:
                break

    import asyncio

    collect_task = asyncio.create_task(collect_commands())
    await asyncio.sleep(0.01)

    # Dispatch high-risk shell_exec
    async with stack_with_bus.sm() as session:
        await stack_with_bus.dispatcher.dispatch(
            session=session,
            principal=stack_with_bus.user_admin,
            targets=HostListSelector([stack_with_bus.host_prod.id]),
            payload=ShellExecPayload(command="echo hello", timeout_s=5),
            idempotency_key=None,
        )
        await session.commit()

    # Wait for event
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Verify event
    assert len(commands_events) >= 1
    event = commands_events[0]
    assert event.channel == "commands"
    assert event.payload["event"] == "command.pending_approval"
    assert event.payload.get("approval_id")
    assert event.payload["actor"] == "user-admin"
    assert event.payload["payload_kind"] == "shell_exec"


@pytest.mark.asyncio
async def test_audit_append_publishes_audit_event(stack_with_bus) -> None:
    """Direct audit append → bus subscriber receives event on 'audit' channel."""
    from server.app.dispatcher.targets import HostListSelector

    # Subscribe to 'audit' channel
    audit_sub = stack_with_bus.bus.subscribe("audit")
    audit_events = []

    async def collect_audit():
        async for event in audit_sub:
            audit_events.append(event)
            if len(audit_events) >= 1:
                break

    import asyncio

    collect_task = asyncio.create_task(collect_audit())
    await asyncio.sleep(0.01)

    # Dispatch reboot (will trigger audit append via audit_chain)
    async with stack_with_bus.sm() as session:
        await stack_with_bus.dispatcher.dispatch(
            session=session,
            principal=stack_with_bus.user_admin,
            targets=HostListSelector([stack_with_bus.host_prod.id]),
            payload=RebootPayload(delay_s=0),
            idempotency_key=None,
        )
        await session.commit()

    # Wait for event
    try:
        await asyncio.wait_for(collect_task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Verify audit event
    assert len(audit_events) >= 1
    event = audit_events[0]
    assert event.channel == "audit"
    assert event.payload["action"] == "command.issued"
    assert event.payload["actor"] == "user-admin"
    assert event.payload.get("sequence") is not None
