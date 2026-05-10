"""ReEnroll gRPC service. TLS-only (no client cert). Ed25519 challenge auth."""
from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

import grpc

from server.app.grpc._pb.fleet.v1 import reenroll_pb2, reenroll_pb2_grpc

log = logging.getLogger(__name__)


class ReEnrollServicer(reenroll_pb2_grpc.ReEnrollServicer):
    TS_SKEW_LIMIT_SECONDS = 60

    def __init__(
        self,
        *,
        session_factory,
        nonce_cache,
        rate_limiter,
        ca,
        ttl_days: int,
    ) -> None:
        self._sm = session_factory
        self._nc = nonce_cache
        self._rl = rate_limiter
        self._ca = ca
        self._ttl_days = ttl_days

    async def Challenge(self, request, context):
        from server.app.models.host import Host

        async with self._sm() as session:
            host = await session.get(Host, request.host_id)
            if host is None:
                log.warning(
                    "reenroll.challenge.unknown host=%s peer=%s",
                    request.host_id,
                    context.peer(),
                )
                await context.abort(
                    grpc.StatusCode.NOT_FOUND, "unknown host_id"
                )
            if not hmac.compare_digest(
                bytes(host.agent_pubkey), bytes(request.signing_pubkey)
            ):
                log.warning(
                    "reenroll.challenge.pubkey_mismatch host=%s peer=%s",
                    request.host_id,
                    context.peer(),
                )
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED, "signing_pubkey mismatch"
                )

        nonce = os.urandom(32)
        self._nc.put(request.host_id, nonce)

        resp = reenroll_pb2.ChallengeResponse(nonce=nonce)
        return resp

    async def Complete(self, request, context):
        from server.app.grpc.cert_rotate_policy import (
            CSRValidationError,
            validate_csr,
        )
        from server.app.grpc.reenroll_state import verify_reenroll_signature
        from server.app.models.host import Host
        from server.app.models.revoked_cert import RevokedCert
        from sqlalchemy import select

        host_id = request.host_id

        if not self._rl.allow(host_id):
            log.warning(
                "reenroll.complete.rate_limited host=%s peer=%s",
                host_id,
                context.peer(),
            )
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED, "reenroll rate limit"
            )

        ts_unix = request.ts.seconds
        now_unix = int(datetime.now(timezone.utc).timestamp())
        if abs(now_unix - ts_unix) > self.TS_SKEW_LIMIT_SECONDS:
            log.warning(
                "reenroll.complete.ts_skew host=%s skew=%d",
                host_id,
                now_unix - ts_unix,
            )
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "ts skew exceeded"
            )

        async with self._sm() as session:
            host = await session.get(Host, host_id)
            if host is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "unknown host_id")

            ok = verify_reenroll_signature(
                host_id=host_id,
                nonce=request.nonce,
                ts_unix=ts_unix,
                signature=request.signature,
                signing_pubkey=bytes(host.agent_pubkey),
            )
            if not ok:
                log.warning(
                    "reenroll.complete.bad_sig host=%s peer=%s",
                    host_id,
                    context.peer(),
                )
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED, "signature invalid"
                )

            if not self._nc.consume(host_id, request.nonce):
                log.warning(
                    "reenroll.complete.bad_nonce host=%s peer=%s",
                    host_id,
                    context.peer(),
                )
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED, "nonce invalid or consumed"
                )

            try:
                validate_csr(request.csr_pem, expected_cn=host_id)
            except CSRValidationError as e:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"csr: {e}")

            chain_pem, new_serial, not_after = self._ca.issue_host_cert(
                request.csr_pem,
                host_id=host_id,
                ttl=timedelta(days=self._ttl_days),
            )

            now = datetime.now(timezone.utc)
            old_serial = host.cert_serial

            # Revoke ALL prior serials for this host (paranoid path)
            prior_serials = (
                await session.execute(
                    select(RevokedCert.serial).where(
                        RevokedCert.host_id == host_id
                    )
                )
            ).scalars().all()
            already_revoked = set(prior_serials)
            if old_serial and old_serial not in already_revoked:
                session.add(
                    RevokedCert(
                        serial=old_serial,
                        host_id=host_id,
                        revoked_at=now,
                        reason="reenrolled",
                    )
                )

            host.cert_serial = new_serial
            host.cert_expires_at = not_after
            host.cert_rotated_at = now
            host.cert_rotation_count = (host.cert_rotation_count or 0) + 1
            host.last_reenroll_at = now

            await session.commit()

            log.info(
                "host_reenrolled host=%s old=%s new=%s peer=%s",
                host_id,
                old_serial,
                new_serial,
                context.peer(),
            )

        from server.app.grpc._pb.fleet.v1 import agent_bridge_pb2

        out = agent_bridge_pb2.CertIssueResponse(cert_chain_pem=chain_pem)
        out.not_after.FromDatetime(not_after)
        return out
