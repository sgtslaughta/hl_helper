"""CommandDispatcher — orchestrates 12-step command pipeline from principal to queue."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from server.app.auth.capability import CapabilityIssuer, CapabilityClaims
from server.app.crypto.signing import SigningBackend
from server.app.dispatcher.queue import CommandQueue
from server.app.dispatcher.risk import classify, RiskLevel
from server.app.dispatcher.sequence import allocate
from server.app.dispatcher.targets import (
    resolve_targets,
    Selector,
    HostListSelector,
    GroupSelector,
    TagSelector,
    MixedSelector,
)
from server.app.events.bus import Bus
from server.app.events.after_commit import publish_after_commit
from server.app.grpc._pb.fleet.v1 import envelope_pb2, commands_pb2
from server.app.models.command import Command, CommandRisk, CommandStatus
from server.app.models.task import Task, TaskKind, TaskRisk, TaskStatus
from server.app.models.task_run import TaskRun, TaskRunStatus
from server.app.audit.sql_chain import SqlAuditChain
from server.app.rbac.provider import Principal, AuthContext
from server.app.rbac.scope import Resource


# ===== Payload Types =====


@dataclass(frozen=True)
class RebootPayload:
    """Reboot command payload."""

    delay_s: int = 0
    reason: str = ""
    payload_kind: ClassVar[str] = "reboot"


@dataclass(frozen=True)
class ShellExecPayload:
    """Shell execution command payload."""

    command: str
    timeout_s: int = 60
    payload_kind: ClassVar[str] = "shell_exec"


@dataclass(frozen=True)
class PkgUpdatePayload:
    """Package update command payload."""

    classes: tuple[str, ...] = ()
    payload_kind: ClassVar[str] = "pkg_update"


@dataclass(frozen=True)
class DispatchResult:
    """Result of dispatch pipeline."""

    task_id: str
    dispatched: list[str] = field(default_factory=list)  # host_ids sent
    denied: list[str] = field(default_factory=list)  # host_ids RBAC-denied
    pending_approval_ids: list[str] = field(default_factory=list)


# ===== Risk Level to Proto Enum Mapping =====


def _risk_to_proto(risk: RiskLevel) -> int:
    """Map risk string to protobuf enum value."""
    mapping = {
        "low": 0,  # RISK_LOW
        "med": 1,  # RISK_MED
        "high": 2,  # RISK_HIGH
    }
    return mapping.get(risk, 2)  # Default to high (2)


# ===== Payload to Proto Mapping =====


def _payload_to_proto(payload: object) -> tuple[str, object]:
    """Convert payload object to (field_name, proto_message) tuple.

    Returns field name (e.g. 'reboot') and constructed proto message.
    """
    if isinstance(payload, RebootPayload):
        return (
            "reboot",
            commands_pb2.Reboot(delay_seconds=payload.delay_s, reason=payload.reason),
        )
    elif isinstance(payload, ShellExecPayload):
        return (
            "shell_exec",
            commands_pb2.ShellExec(
                command=payload.command, timeout_seconds=payload.timeout_s
            ),
        )
    elif isinstance(payload, PkgUpdatePayload):
        return (
            "pkg_update",
            commands_pb2.PkgUpdate(classes=payload.classes),
        )
    else:
        raise TypeError(f"unsupported payload type: {type(payload).__name__}")


def _payload_to_dict(payload: object) -> dict[str, object]:
    """Convert payload object to dict for Task.payload storage."""
    if isinstance(payload, RebootPayload):
        return {"delay_s": payload.delay_s, "reason": payload.reason}
    elif isinstance(payload, ShellExecPayload):
        return {"command": payload.command, "timeout_s": payload.timeout_s}
    elif isinstance(payload, PkgUpdatePayload):
        return {"classes": list(payload.classes)}
    else:
        raise TypeError(f"unsupported payload type: {type(payload).__name__}")


def _selector_to_dict(targets: Selector) -> dict[str, object]:
    """Convert Selector object to dict for Task.target_selector storage."""
    if isinstance(targets, HostListSelector):
        return {"host_ids": targets.host_ids}
    elif isinstance(targets, GroupSelector):
        return {
            "group_id": str(targets.group_id),
            "include_subgroups": targets.include_subgroups,
        }
    elif isinstance(targets, TagSelector):
        return {"tag": {"key": targets.key, "value": targets.value}}
    elif isinstance(targets, MixedSelector):
        return {"selectors": [_selector_to_dict(s) for s in targets.selectors]}
    else:
        raise TypeError(f"unsupported selector type: {type(targets).__name__}")


def _principal_identity(principal: Principal) -> str:
    """Return a non-empty identity string for the principal.

    Raises ValueError if neither user_id nor service_account_id is set.
    The result is signed into the capability biscuit and recorded as the
    audit actor — anonymous-but-trusted principals must not be allowed here.
    """
    ident = principal.user_id or principal.service_account_id
    if not ident:
        raise ValueError("principal has no identity (user_id or service_account_id required)")
    return ident


# ===== CommandDispatcher =====


class CommandDispatcher:
    """Orchestrates command dispatch pipeline.

    12-step pipeline:
    1. Resolve targets via selector
    2. RBAC filter per host
    3. Risk classify
    4. Approval gating (if required)
    5. Idempotency check
    6. Create TaskRun
    7. Allocate per-host sequence
    8. Build CommandEnvelope proto
    9. Sign envelope
    10. Persist Command row
    11. Audit append
    12. Return DispatchResult

    Caller commits the session.
    """

    def __init__(
        self,
        *,
        queue: CommandQueue,
        audit: SqlAuditChain,
        capability_issuer: CapabilityIssuer,
        signing_backend: SigningBackend,
        approval_engine: Any,  # ApprovalEngine-like; duck-typed for tests
        rbac_provider: Any,
        scope_evaluator: Any,  # reserved; not yet used
        event_bus: Bus | None = None,
    ) -> None:
        """Initialize dispatcher with collaborators.

        Args:
            queue: Durable command queue.
            audit: Audit chain for logging.
            capability_issuer: Biscuit capability issuer.
            signing_backend: Signing backend for envelope signatures.
            approval_engine: Approval engine (duck-typed).
            rbac_provider: RBAC decision provider.
            scope_evaluator: Reserved for future scope evaluation.
            event_bus: Optional event bus for publishing dispatch events.
        """
        self._queue = queue
        self._audit = audit
        self._capability_issuer = capability_issuer
        self._signing_backend = signing_backend
        self._approval_engine = approval_engine
        self._rbac_provider = rbac_provider
        self._scope_evaluator = scope_evaluator
        self._event_bus = event_bus

    async def dispatch(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        targets: Selector,
        payload: object,
        idempotency_key: str | None = None,
    ) -> DispatchResult:
        """Execute 12-step dispatch pipeline.

        Args:
            session: AsyncSession for DB operations
            principal: Principal making the request
            targets: Selector (GroupSelector, TagSelector, HostListSelector, MixedSelector)
            payload: Command payload (RebootPayload, ShellExecPayload, etc.)
            idempotency_key: Optional key for idempotent dispatch

        Returns:
            DispatchResult with task_id, dispatched host_ids, denied host_ids, pending_approval_ids
        """

        # Step 1: Resolve targets
        all_hosts = await resolve_targets(session, targets)

        # Step 2: RBAC filter — partition into dispatched_candidates and denied
        dispatched_candidates = []
        denied = []
        payload_kind = self._get_payload_kind(payload)
        # Map dispatcher payload_kind to RBAC catalog action name.
        # Catalog uses "host:exec" for arbitrary shell, etc.
        _action_name = {
            "shell_exec": "host:exec",
            "reboot": "host:reboot",
            "shutdown": "host:shutdown",
            "pkg_update": "host:pkg_update",
        }.get(payload_kind, f"host:{payload_kind}")

        for host_id in all_hosts:
            # Check if principal has host:<action> permission on this host.
            # Fail-closed: any provider exception denies the host.
            resource = Resource(id=host_id)
            ctx = AuthContext()
            try:
                decision = await self._rbac_provider.is_authorized(
                    principal, _action_name, resource, ctx
                )
                if decision.allow:
                    dispatched_candidates.append(host_id)
                else:
                    denied.append(host_id)
            except Exception as e:
                import structlog
                structlog.get_logger().exception(
                    "rbac_provider_exception",
                    host_id=host_id,
                    action=_action_name,
                    exc=e,
                )
                denied.append(host_id)

        # Step 3: Risk classify
        risk = classify(
            payload_kind,
            len(dispatched_candidates),
            payload_metadata=self._extract_payload_metadata(payload),
        )

        # Get principal identity early for approval event and audit
        principal_id = _principal_identity(principal)

        # Step 3.5: Persist parent Task row early so it shows in /v1/tasks
        # even while waiting for approval or even when RBAC denied every host.
        # task_id reused across approval/idempotency/early-exit branches.
        early_task_id = str(uuid4())
        early_task = Task(
            id=early_task_id,
            kind=TaskKind(payload_kind),
            payload=_payload_to_dict(payload),
            target_selector=_selector_to_dict(targets),
            idempotency_key=idempotency_key,
            risk=TaskRisk(risk),
            requires_approval=(risk == "high"),
            created_by=principal_id,
            status=TaskStatus.PENDING,
        )
        session.add(early_task)
        await session.flush()

        # Step 4: Approval gating — high-risk dispatches require an approved row
        # before any host is enqueued. Pending approvals returned to caller.
        pending_approval_ids: list[str] = []
        if risk == "high" and self._approval_engine is not None and dispatched_candidates:
            from server.app.models import Approval
            from server.app.models.approval import ApprovalState
            from sqlalchemy import select as _select

            existing_q = await session.execute(
                _select(Approval).where(
                    Approval.subject_type == "command",
                    Approval.subject_id == payload_kind,
                    Approval.requester_id == _principal_identity(principal),
                    Approval.state == ApprovalState.APPROVED,
                ).limit(1)
            )
            approved_row = existing_q.scalars().first()
            if approved_row is None:
                # Auto-self-approve when principal holds task:approve perm.
                # Lets admin/owner shell-exec dispatch immediately so a TaskRun
                # is created and the task becomes visible in per-host UI.
                self_approved = False
                try:
                    decision = await self._rbac_provider.is_authorized(
                        principal,
                        "task:approve",
                        Resource(),
                        AuthContext(),
                    )
                    self_approved = bool(decision.allow)
                except Exception:
                    self_approved = False

                if self_approved:
                    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                    auto_row = Approval(
                        id=str(uuid4()),
                        subject_type="command",
                        subject_id=payload_kind,
                        policy="single",
                        requester_id=_principal_identity(principal),
                        state=ApprovalState.APPROVED,
                        decided_by_id=_principal_identity(principal),
                        decided_at=_dt.now(_tz.utc),
                        expires_at=_dt.now(_tz.utc) + _td(hours=1),
                    )
                    session.add(auto_row)
                    await session.flush()
                    # Fall through into TaskRun creation below.
                else:
                    pending = await self._approval_engine.request(
                        subject_type="command",
                        subject_id=payload_kind,
                        policy="single_second_factor",
                        requester_id=_principal_identity(principal),
                    )
                    pending_approval_ids.append(pending.id)

                    # Publish pending approval event if bus is set
                    if self._event_bus is not None:
                        publish_after_commit(
                            session,
                            self._event_bus,
                            "commands",
                            {
                                "event": "command.pending_approval",
                                "approval_id": pending.id,
                                "actor": principal_id,
                                "payload_kind": payload_kind,
                            },
                        )

                    # Block dispatch when no approval is in hand
                    await session.commit()
                    return DispatchResult(
                        task_id=early_task_id,
                        dispatched=[],
                        denied=denied,
                        pending_approval_ids=pending_approval_ids,
                    )

        # Early exit when no candidates survived RBAC: no TaskRun, no FK violation.
        if not dispatched_candidates:
            await session.commit()
            return DispatchResult(
                task_id=early_task_id,
                dispatched=[],
                denied=denied,
                pending_approval_ids=pending_approval_ids,
            )

        # Step 5: Idempotency check — look up by stored idempotency_key, not queue head.
        task_run_id: str | None = None
        task_id: str | None = None
        if idempotency_key is not None:
            cached_id = self._queue._idempotency_cache.get(idempotency_key)
            if cached_id is not None:
                from server.app.models.command import Command as _Cmd

                cached_cmd = await session.get(_Cmd, cached_id)
                if cached_cmd is not None:
                    task_run_id = cached_cmd.task_run_id
                    task_run = await session.get(TaskRun, task_run_id)
                    if task_run is not None:
                        task_id = task_run.task_id

        # Step 6: Create TaskRun — one per dispatch call, aggregating all commands.
        # Reuse the early-created Task; only mint a TaskRun when not resuming
        # an idempotency-keyed prior dispatch.
        if task_run_id is None:
            task_id = early_task_id
            task_run_id = str(uuid4())
            task_run = TaskRun(
                id=task_run_id,
                task_id=task_id,
                host_id=dispatched_candidates[0],
                status=TaskRunStatus.PENDING,
            )
            session.add(task_run)
            await session.flush()

        commands_created = []

        # Steps 7-11 per host.
        now = datetime.now(timezone.utc)

        for host_id in dispatched_candidates:
            # Step 7: Allocate sequence
            sequence = await allocate(session, host_id)

            # Step 8: Build CommandEnvelope
            command_id = str(uuid4())
            nonce = os.urandom(16)
            issued_at = now
            # TTL: take ShellExec.timeout_s when present, else 300s default.
            # Add a 30s slack so the server-side sweeper doesn't race the
            # agent's own timeout.
            payload_to = (
                payload.timeout_s
                if isinstance(payload, ShellExecPayload) and payload.timeout_s > 0
                else 300
            )
            expires_at = now + timedelta(seconds=payload_to + 30)

            # Build capability claims
            claims = CapabilityClaims(
                host_id=host_id,
                action=payload_kind,
                resource=None,
                issued_at=issued_at,
                expires_at=expires_at,
                issuer=principal_id,
            )
            capability_bytes = self._capability_issuer.issue(claims)

            # Build envelope proto
            envelope = envelope_pb2.CommandEnvelope(
                command_id=command_id,
                host_id=host_id,
                sequence=sequence,
                nonce=nonce,
                issued_by=principal_id,
            )
            # Proto enum value from generated module — use the int constant directly
            # via setattr to bypass type-stub strictness on the enum field type.
            setattr(envelope, "risk", _risk_to_proto(risk))
            # Set timestamps
            envelope.issued_at.FromDatetime(issued_at)
            envelope.expires_at.FromDatetime(expires_at)

            # Set capability
            envelope.capability.biscuit = capability_bytes
            envelope.capability.declared_scopes.append(f"host:{host_id}")
            envelope.capability.declared_scopes.append(f"action:{payload_kind}")

            # Set payload oneof — proto submessages require CopyFrom, not setattr
            field_name, proto_payload = _payload_to_proto(payload)
            getattr(envelope, field_name).CopyFrom(proto_payload)

            # Step 9: Sign envelope
            # Serialize envelope without signature, sign, then add signature
            envelope_copy = envelope_pb2.CommandEnvelope()
            envelope_copy.CopyFrom(envelope)
            envelope_copy.ClearField("signature")
            serialized = envelope_copy.SerializeToString()
            signature = self._signing_backend.sign(serialized)
            envelope.signature = signature

            # Step 10: Persist Command row
            envelope_bytes = envelope.SerializeToString()
            command = Command(
                id=command_id,
                task_run_id=task_run_id,
                host_id=host_id,
                sequence=sequence,
                envelope_bytes=envelope_bytes,
                risk=CommandRisk(risk),
                issued_at=issued_at,
                expires_at=expires_at,
                status=CommandStatus.QUEUED,
            )
            enqueued_cmd = await self._queue.enqueue(
                session, command, idempotency_key=idempotency_key
            )
            commands_created.append(enqueued_cmd)

            # Step 11: Audit append — only if this is a new command
            if enqueued_cmd.id == command_id:
                # Metric: command dispatched (verb, risk)
                try:
                    from server.app.observability.metrics import (
                        fleet_command_dispatched_total,
                    )
                    fleet_command_dispatched_total.labels(
                        verb=payload_kind, risk=risk
                    ).inc()
                except Exception:
                    pass
                await self._audit.append(
                    session,
                    actor=principal_id,
                    action="command.issued",
                    subject=command_id,
                    payload={
                        "host_id": host_id,
                        "task_run_id": task_run_id,
                        "risk": risk,
                        "payload_kind": payload_kind,
                        "command_id": command_id,
                    },
                )

                # Publish command.issued event if bus is set
                if self._event_bus is not None:
                    publish_after_commit(
                        session,
                        self._event_bus,
                        "commands",
                        {
                            "event": "command.issued",
                            "command_id": command_id,
                            "host_id": host_id,
                            "task_run_id": task_run_id,
                            "risk": risk,
                            "payload_kind": payload_kind,
                            "actor": principal_id,
                        },
                    )

        # Step 12: Return DispatchResult
        return DispatchResult(
            task_id=task_id or "",
            dispatched=dispatched_candidates,
            denied=denied,
            pending_approval_ids=pending_approval_ids,
        )

    def _get_payload_kind(self, payload: object) -> str:
        """Extract payload_kind from payload object."""
        kind = getattr(payload, "payload_kind", None)
        if isinstance(kind, str):
            return kind
        raise TypeError(f"payload has no payload_kind: {type(payload).__name__}")

    def _extract_payload_metadata(self, payload: object) -> dict[str, Any]:
        """Extract metadata from payload for risk classification."""
        if isinstance(payload, PkgUpdatePayload):
            return {"classes": payload.classes}
        return {}
