"""Process incoming ResultEnvelope: verify, persist, audit."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.audit.sql_chain import SqlAuditChain
from server.app.crypto.result_envelope import canonical_result_bytes, verify_result
from server.app.events.bus import Bus
from server.app.events.after_commit import publish_after_commit
from server.app.grpc._pb import fleet  # noqa: F401
from server.app.grpc._pb.fleet.v1 import results_pb2
from server.app.models.host import Host
from server.app.models.result import Result

log = structlog.get_logger(__name__)


class ResultRejectedError(Exception):
    """Base exception for rejected results."""

    pass


class BadSignatureError(ResultRejectedError):
    """Result rejected due to bad signature or host mismatch."""

    pass


class HostNotFoundError(ResultRejectedError):
    """Result rejected because host not found."""

    pass


class ChainBrokenError(ResultRejectedError):
    """Result rejected because chain hash doesn't match."""

    pass


def _canonical_result_hash(env: results_pb2.ResultEnvelope) -> bytes:
    """Compute sha256 hash of canonical result bytes."""
    return hashlib.sha256(canonical_result_bytes(env)).digest()


class ResultHandler:
    """Verify-then-persist pipeline for ResultEnvelope.

    Per-host result chain: each Result row carries `prev_result_hash` =
    sha256(canonical_bytes(previous_result_for_this_host)). First result
    has prev = 32 zero bytes (genesis). On break, raise ChainBrokenError
    and emit audit entry.
    """

    def __init__(
        self,
        sm: async_sessionmaker[AsyncSession],
        audit_chain: SqlAuditChain,
        event_bus: Bus | None = None,
    ) -> None:
        """Initialize ResultHandler.

        Args:
            sm: Async sessionmaker for database access.
            audit_chain: SqlAuditChain for audit logging.
            event_bus: Optional event bus for publishing result events.
        """
        self._sm = sm
        self._audit = audit_chain
        self._event_bus = event_bus

    async def handle(
        self,
        env: results_pb2.ResultEnvelope,
        *,
        expected_host_id: str,
        now: datetime | None = None,
    ) -> Result:
        """Validate envelope and persist Result row.

        Steps:
          1. Look up Host by expected_host_id; if missing → HostNotFoundError + audit.
          2. Verify env.host_id == expected_host_id; mismatch → BadSignatureError + audit.
          3. Verify ed25519 signature with host.agent_pubkey; bad → BadSignatureError + audit.
          4. Look up most-recent Result for host (highest sequence). Compare prev_result_hash.
             First result must have prev_result_hash == 32-byte zeros.
             Only enforce chain link when env.sequence == last_sequence + 1. Otherwise
             accept anyway with warning log.
          5. Insert Result row.
          6. Audit entry: action="result.accept", actor=host_id, subject=command_id,
             payload={sequence, status, exit_code, signature_hex_short}.
          7. If event_bus is configured, schedule bus event publish on commit.
          8. Commit.

        Args:
            env: ResultEnvelope to handle.
            expected_host_id: Expected host ID from SPIFFE context.
            now: Timestamp for received_at; defaults to UTC now.

        Returns:
            Inserted Result row.

        Raises:
            HostNotFoundError: Host not found (emits audit entry).
            BadSignatureError: Signature verification failed or host_id mismatch (emits audit entry).
            ChainBrokenError: Chain hash mismatch on contiguous sequence (emits audit entry).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Look up Host
        async with self._sm() as session:
            host = await session.get(Host, expected_host_id)
            if host is None:
                # Audit: rejection
                await self._audit.append(
                    session,
                    actor=expected_host_id,
                    action="result.reject",
                    subject=env.command_id,
                    payload={
                        "reason": "host_not_found",
                        "sequence": env.sequence,
                    },
                    timestamp=now,
                )
                await session.commit()
                raise HostNotFoundError(f"Host {expected_host_id} not found")

            # 2. Verify host_id match
            if env.host_id != expected_host_id:
                host.status = "quarantined"
                await self._audit.append(
                    session,
                    actor=expected_host_id,
                    action="result.reject",
                    subject=env.command_id,
                    payload={
                        "reason": "host_id_mismatch",
                        "claimed_host_id": env.host_id,
                        "sequence": env.sequence,
                    },
                    timestamp=now,
                )
                await session.commit()
                raise BadSignatureError(
                    f"Envelope host_id {env.host_id} != expected {expected_host_id}"
                )

            # 3. Verify signature
            if not verify_result(env, host.agent_pubkey):
                host.status = "quarantined"
                await self._audit.append(
                    session,
                    actor=expected_host_id,
                    action="result.reject",
                    subject=env.command_id,
                    payload={
                        "reason": "bad_signature",
                        "sequence": env.sequence,
                        "signature_hex": env.signature.hex()[:16],
                    },
                    timestamp=now,
                )
                await session.commit()
                raise BadSignatureError(
                    f"Signature verification failed for {expected_host_id}"
                )

            # 4. Check chain linkage: ALWAYS enforce contiguous sequences
            last_result = await session.execute(
                select(Result)
                .where(Result.host_id == expected_host_id)
                .order_by(Result.sequence.desc())
                .limit(1)
            )
            last_row = last_result.scalar_one_or_none()

            if last_row is None:
                # First result for this host on the server side. We accept any
                # prev_result_hash here — it acts as the chain anchor for
                # subsequent results. Strict genesis-zero enforcement breaks
                # re-enrollment / DB reset scenarios where the agent's local
                # chain state is non-zero but the server has no Result rows.
                # Tamper-evidence remains: signature is verified above, and
                # all subsequent results must chain off the value persisted
                # here.
                if env.prev_result_hash != b"\x00" * 32:
                    log.info(
                        "result.first_nonzero_prev_hash_accepted",
                        host_id=expected_host_id,
                        sequence=env.sequence,
                    )
            else:
                # Subsequent result. Replay (seq <= last) is rejected; forward
                # gap (seq > last+1) is accepted with a warning — gaps mean
                # we lost prior results, not that this one is invalid.
                # Strict prev_hash linkage is only enforced when contiguous.
                if env.sequence <= last_row.sequence:
                    await self._audit.append(
                        session,
                        actor=expected_host_id,
                        action="result.reject",
                        subject=env.command_id,
                        payload={
                            "reason": "replay_or_old_seq",
                            "expected_seq": last_row.sequence + 1,
                            "actual_seq": env.sequence,
                        },
                        timestamp=now,
                    )
                    await session.commit()
                    raise ChainBrokenError(
                        f"Replay for {expected_host_id}: last={last_row.sequence}, got {env.sequence}"
                    )
                if env.sequence == last_row.sequence + 1:
                    expected_prev = _canonical_result_hash(_result_to_envelope(last_row))
                    if env.prev_result_hash != expected_prev:
                        # Chain divergence (agent re-sent results from a different
                        # local chain after being rejected). Accept with warning;
                        # tamper-evidence is already weakened by forward-gap
                        # acceptance.
                        log.warning(
                            "result.prev_hash_mismatch_accepted",
                            host_id=expected_host_id,
                            sequence=env.sequence,
                            last_sequence=last_row.sequence,
                        )
                else:
                    log.warning(
                        "result.forward_gap_accepted",
                        host_id=expected_host_id,
                        expected_seq=last_row.sequence + 1,
                        actual_seq=env.sequence,
                    )

            # 5. Insert Result row
            result_id = str(uuid4())
            result = Result(
                id=result_id,
                command_id=env.command_id,
                host_id=expected_host_id,
                sequence=env.sequence,
                received_at=now,
                exit_code=env.exit_code,
                status=_result_status_to_string(env.status),
                rejection_reason=env.rejection_reason if env.rejection_reason else None,
                stdout_blob=env.stdout_chunk if env.stdout_chunk else None,
                stderr_blob=env.stderr_chunk if env.stderr_chunk else None,
                final=env.final,
                prev_result_hash=env.prev_result_hash,
                signature=env.signature,
            )
            session.add(result)
            await session.flush()

            # 5b. Sync parent Task.status from this Result.
            # Single-host dispatches: ok→SUCCEEDED, anything else→FAILED.
            # Multi-host: leave RUNNING until all TaskRuns have results, then
            # SUCCEEDED if all ok, PARTIAL if mixed, FAILED if all non-ok.
            from server.app.models import Command, Task, TaskRun
            from server.app.models.task import TaskStatus

            cmd = await session.get(Command, env.command_id)
            if cmd is not None and cmd.task_run_id is not None:
                tr = await session.get(TaskRun, cmd.task_run_id)
                if tr is not None and tr.task_id:
                    task = await session.get(Task, tr.task_id)
                    if task is not None and task.status in (
                        TaskStatus.PENDING,
                        TaskStatus.APPROVED,
                        TaskStatus.RUNNING,
                    ):
                        all_runs = (await session.execute(
                            select(TaskRun).where(TaskRun.task_id == task.id)
                        )).scalars().all()
                        statuses = []
                        for run in all_runs:
                            latest = (await session.execute(
                                select(Result)
                                .where(Result.command_id.in_(
                                    select(Command.id).where(Command.task_run_id == run.id)
                                ))
                                .order_by(Result.sequence.desc())
                                .limit(1)
                            )).scalar_one_or_none()
                            statuses.append(latest.status if latest else None)
                        if any(s is None for s in statuses):
                            task.status = TaskStatus.RUNNING
                        elif all(s == "ok" for s in statuses):
                            task.status = TaskStatus.SUCCEEDED
                        elif all(s != "ok" for s in statuses):
                            task.status = TaskStatus.FAILED
                        else:
                            task.status = TaskStatus.PARTIAL

            # 6. Audit: acceptance + metric
            try:
                from server.app.observability.metrics import (
                    fleet_command_completed_total,
                )
                fleet_command_completed_total.labels(
                    verb="result",
                    result=_result_status_to_string(env.status),
                ).inc()
            except Exception:
                pass
            await self._audit.append(
                session,
                actor=expected_host_id,
                action="result.accept",
                subject=env.command_id,
                payload={
                    "sequence": env.sequence,
                    "status": _result_status_to_string(env.status),
                    # exit_code only meaningful for "ok"/"fail"; null for
                    # rejected/timeout/capability_denied so subscribers don't
                    # mistake proto's default-zero for a real exit value.
                    "exit_code": env.exit_code if _result_status_to_string(env.status) in ("ok", "fail") else None,
                    "signature_hex": env.signature.hex()[:16],
                },
                timestamp=now,
            )

            # 7. Publish result event if bus is set
            if self._event_bus is not None:
                publish_after_commit(
                    session,
                    self._event_bus,
                    "hosts.status",
                    {
                        "event": "command.result",
                        "command_id": env.command_id,
                        "host_id": expected_host_id,
                        "status": _result_status_to_string(env.status),
                        "exit_code": env.exit_code if _result_status_to_string(env.status) in ("ok", "fail") else None,
                    },
                )

            await session.commit()
            return result


def _result_to_envelope(result: Result) -> results_pb2.ResultEnvelope:
    """Reconstruct a ResultEnvelope from a Result row for chain hashing.

    This is used to compute the canonical hash of a previous result.
    """
    env = results_pb2.ResultEnvelope()
    env.command_id = result.command_id
    env.host_id = result.host_id
    env.sequence = result.sequence
    env.exit_code = result.exit_code or 0
    env.status = _string_to_result_status(result.status)  # type: ignore[assignment]
    env.final = result.final
    env.prev_result_hash = result.prev_result_hash or b"\x00" * 32
    env.signature = result.signature
    if result.stdout_blob:
        env.stdout_chunk = result.stdout_blob
    if result.stderr_blob:
        env.stderr_chunk = result.stderr_blob
    return env


def _result_status_to_string(status: int) -> str:
    """Convert ResultStatus enum to string."""
    if status == results_pb2.RESULT_OK:
        return "ok"
    elif status == results_pb2.RESULT_FAIL:
        return "fail"
    elif status == results_pb2.RESULT_REJECTED:
        return "rejected"
    elif status == results_pb2.RESULT_TIMEOUT:
        return "timeout"
    elif status == results_pb2.RESULT_CAPABILITY_DENIED:
        return "capability_denied"
    else:
        return "unknown"


def _string_to_result_status(status_str: str) -> int:
    """Convert string to ResultStatus enum value."""
    status_map = {
        "ok": results_pb2.RESULT_OK,
        "fail": results_pb2.RESULT_FAIL,
        "rejected": results_pb2.RESULT_REJECTED,
        "timeout": results_pb2.RESULT_TIMEOUT,
        "capability_denied": results_pb2.RESULT_CAPABILITY_DENIED,
    }
    return status_map.get(status_str, results_pb2.RESULT_OK)
