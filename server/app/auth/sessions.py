"""Session service — opaque token sessions with IP/UA binding, TTL, and event-based revocation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address, ip_network
from typing import Any, cast

import cachetools
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.events.bus import Bus
from server.app.models import Session, User

logger = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    """Coerce naive datetime to UTC-aware (SQLite returns naive)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


PREFIX = "hls_"
IDLE_TTL_SECONDS = 30 * 60
ABSOLUTE_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class RequestMeta:
    """Request context: IP and User-Agent fingerprint."""

    ip: str
    ua: str

    def ip_class(self) -> str:
        """Return CIDR /24 for IPv4, /48 for IPv6; invalid returns full IP."""
        try:
            addr = ip_address(self.ip)
            if addr.version == 4:
                net = ip_network(f"{self.ip}/24", strict=False)
            else:
                net = ip_network(f"{self.ip}/48", strict=False)
            return str(net)
        except ValueError:
            return self.ip

    def ua_fp(self) -> bytes:
        """Return SHA-256 fingerprint of user agent."""
        return hashlib.sha256(self.ua.encode("utf-8")).digest()


def make_request_meta(ip: str, ua: str) -> RequestMeta:
    """Helper to create RequestMeta from IP and UA strings."""
    return RequestMeta(ip=ip, ua=ua)


@dataclass(frozen=True)
class SessionIssue:
    """Result of issue() — returned raw token ONCE."""

    raw: str
    session_id: str
    expires_at: datetime


def _generate_token() -> str:
    """Generate hls_<32 url-safe bytes> token."""
    raw = secrets.token_bytes(32)
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return PREFIX + body


def _hash_token(token: str) -> bytes:
    """Return SHA-256 hash of token."""
    return hashlib.sha256(token.encode("utf-8")).digest()


class SessionService:
    """Issue, lookup, and revoke sessions with TTL and event-based invalidation."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[Any],
        bus: Bus,
        idle_ttl_seconds: int = IDLE_TTL_SECONDS,
        absolute_ttl_seconds: int = ABSOLUTE_TTL_SECONDS,
        cache_size: int = 10000,
        cache_ttl: int = 30,
    ) -> None:
        """Initialize SessionService.

        Args:
            sessionmaker: AsyncSession factory.
            bus: Event bus for subscriptions.
            idle_ttl_seconds: Idle timeout (default 30 min).
            absolute_ttl_seconds: Absolute session lifetime (default 12 h).
            cache_size: Max cached sessions (default 10000).
            cache_ttl: Cache entry TTL in seconds (default 30).
        """
        self._sessionmaker = sessionmaker
        self._bus = bus
        self._idle_ttl = timedelta(seconds=idle_ttl_seconds)
        self._absolute_ttl = timedelta(seconds=absolute_ttl_seconds)
        self._cache: cachetools.TTLCache[str, Session] = cachetools.TTLCache(
            maxsize=cache_size, ttl=cache_ttl
        )
        self._subscription_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the service and subscribe to rbac.binding_changed events."""
        self._subscription_task = asyncio.create_task(self._run_subscription())

    async def stop(self) -> None:
        """Stop the service and cancel subscription."""
        if self._subscription_task:
            self._subscription_task.cancel()
            try:
                await self._subscription_task
            except asyncio.CancelledError:
                pass

    async def _run_subscription(self) -> None:
        """Subscribe to rbac.binding_changed and revoke all sessions for affected user."""
        sub = self._bus.subscribe("rbac.binding_changed")
        try:
            async for event in sub:
                try:
                    user_id = event.payload.get("user_id")
                    if user_id:
                        await self._revoke_user_sessions(user_id)
                except Exception as exc:
                    logger.exception("Error processing rbac.binding_changed event: %s", exc)
        except asyncio.CancelledError:
            await sub.close()
            raise

    async def _revoke_user_sessions(self, user_id: str) -> None:
        """Revoke all sessions for a user by setting revoked_at."""
        now = datetime.now(timezone.utc)
        async with self._sessionmaker() as db_session:
            recs = (
                await db_session.execute(
                    select(Session).where(Session.user_id == user_id)
                )
            ).scalars().all()
            for rec in recs:
                rec.revoked_at = now
            await db_session.commit()
        for key in list(self._cache.keys()):
            cached = self._cache[key]
            if cached.user_id == user_id:
                del self._cache[key]

    async def issue(
        self, user: User, mfa_level: str, request_meta: RequestMeta
    ) -> SessionIssue:
        """Issue a new session token.

        Args:
            user: User object with id.
            mfa_level: MFA level (e.g., "totp", "none").
            request_meta: Request metadata (IP and UA).

        Returns:
            SessionIssue with raw token (returned ONCE), session_id, expires_at.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + self._absolute_ttl

        raw_token = _generate_token()
        token_hash = _hash_token(raw_token)
        ip_class = request_meta.ip_class()
        ua_fp = request_meta.ua_fp()

        async with self._sessionmaker() as session:
            db_session = Session(
                user_id=user.id,
                token_hash=token_hash,
                mfa_level=mfa_level,
                ip_class=ip_class,
                ua_fp=ua_fp,
                expires_at=expires_at,
            )
            session.add(db_session)
            await session.commit()
            session_id = db_session.id

        return SessionIssue(raw=raw_token, session_id=session_id, expires_at=expires_at)

    async def lookup(
        self, raw_token: str, request_meta: RequestMeta | None = None
    ) -> Session | None:
        """Lookup a session by token, validating TTL and request metadata.

        Args:
            raw_token: Plaintext token.
            request_meta: Optional request metadata for IP/UA validation.

        Returns:
            Session row if valid; None if expired, revoked, or validation failed.
        """
        token_hash = _hash_token(raw_token)
        cache_key = token_hash.hex()

        now = datetime.now(timezone.utc)

        if cache_key in self._cache:
            cached_session = self._cache[cache_key]
            if cached_session.revoked_at is not None:
                del self._cache[cache_key]
                return None

            if now > _aware(cached_session.expires_at):
                del self._cache[cache_key]
                return None

            last_used = _aware(cached_session.last_used_at or cached_session.issued_at)
            if now - last_used > self._idle_ttl:
                del self._cache[cache_key]
                return None

            if request_meta is not None:
                if not self._validate_request_meta(cached_session, request_meta):
                    return None

            await self._update_last_used(cached_session.id, now)
            cached_session.last_used_at = now
            self._cache[cache_key] = cached_session
            return cached_session

        async with self._sessionmaker() as db_session:
            rec = await db_session.scalar(
                select(Session).where(Session.token_hash == token_hash)
            )

        if rec is None:
            return None

        if rec.revoked_at is not None:
            return None

        expires_at = _aware(rec.expires_at)
        if now > expires_at:
            return None

        last_used = _aware(rec.last_used_at or rec.issued_at)
        if now - last_used > self._idle_ttl:
            return None

        if request_meta is not None:
            if not self._validate_request_meta(rec, request_meta):
                return None

        await self._update_last_used(rec.id, now)
        rec.last_used_at = now

        self._cache[cache_key] = rec
        return cast(Session, rec)

    def _validate_request_meta(self, session: Session, request_meta: RequestMeta) -> bool:
        """Validate that request_meta matches session binding."""
        try:
            req_addr = ip_address(request_meta.ip)
            sess_net = ip_network(session.ip_class, strict=False)
            if req_addr not in sess_net:
                return False
        except ValueError:
            return False

        if request_meta.ua_fp() != session.ua_fp:
            return False

        return True

    async def _update_last_used(self, session_id: str, now: datetime) -> None:
        """Update last_used_at timestamp for a session."""
        async with self._sessionmaker() as db_session:
            await db_session.execute(
                update(Session).where(Session.id == session_id).values(last_used_at=now)
            )
            await db_session.commit()

    async def revoke(self, session_id: str, reason: str) -> None:
        """Revoke a session immediately.

        Args:
            session_id: Session ID to revoke.
            reason: Reason for revocation (for audit).
        """
        now = datetime.now(timezone.utc)

        async with self._sessionmaker() as db_session:
            rec = await db_session.scalar(
                select(Session).where(Session.id == session_id)
            )
            if rec:
                rec.revoked_at = now
                await db_session.commit()

        for key in list(self._cache.keys()):
            cached = self._cache[key]
            if cached.id == session_id:
                del self._cache[key]
                break

        await self._bus.publish("session.revoked", {"session_id": session_id, "reason": reason})
