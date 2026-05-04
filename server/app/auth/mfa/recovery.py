"""Recovery codes service — generate, consume, and track one-time-use backup codes."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from server.app.models.user import User


class RecoveryCooldown(Exception):
    """Raised when too many wrong recovery code attempts are made within cooldown period."""

    pass


@dataclass
class RecoveryStatus:
    """Status of recovery codes for a user."""

    total: int
    consumed: int
    remaining: int
    viewed: bool


class RecoveryService:
    """Recovery code service — generate, consume, and manage backup codes."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        """Initialize RecoveryService.

        Args:
            sessionmaker: SQLAlchemy async sessionmaker for database access.
        """
        self._sessionmaker = sessionmaker
        self._cooldowns: dict[str, tuple[float, int]] = {}  # user_id -> (expires_at, fail_count)

    async def generate(self, user: User, count: int = 10) -> list[str]:
        """Generate recovery codes and store hashed versions in database.

        Args:
            user: User to generate codes for.
            count: Number of codes to generate (default 10).

        Returns:
            List of plaintext codes (caller responsible for showing once).
        """
        from server.app.models.recovery_code import RecoveryCode

        codes: list[str] = []
        rows: list[RecoveryCode] = []

        # Generate plaintext codes and hashes
        for _ in range(count):
            left = secrets.token_hex(4)  # 8 hex chars
            right = secrets.token_hex(4)  # 8 hex chars
            code = f"{left}-{right}"
            codes.append(code)

            # Hash the code
            code_hash = hashlib.sha256(code.encode()).digest()

            # Create row (don't save plaintext)
            rows.append(RecoveryCode(user_id=user.id, code_hash=code_hash))

        # Store hashed rows in DB
        async with self._sessionmaker() as session:
            session.add_all(rows)
            await session.commit()

        return codes

    async def regenerate(self, user: User, count: int = 10) -> list[str]:
        """Delete all existing codes and generate new set.

        Args:
            user: User to regenerate codes for.
            count: Number of codes to generate (default 10).

        Returns:
            List of plaintext codes for the new set.
        """
        from server.app.models.recovery_code import RecoveryCode

        async with self._sessionmaker() as session:
            await session.execute(
                delete(RecoveryCode).where(RecoveryCode.user_id == user.id)
            )
            await session.commit()

        return await self.generate(user, count)

    async def consume(self, user: User, code: str) -> bool:
        """Consume (use) a recovery code.

        Args:
            user: User attempting to consume code.
            code: Plaintext recovery code.

        Returns:
            True if code was valid and consumed; False if code not found or already consumed.

        Raises:
            RecoveryCooldown: If user has exceeded 3 wrong attempts in 60 seconds.
        """
        from server.app.models.recovery_code import RecoveryCode

        # Check cooldown
        now = time.time()
        if user.id in self._cooldowns:
            expires_at, fail_count = self._cooldowns[user.id]
            if now < expires_at and fail_count >= 3:
                raise RecoveryCooldown("Too many failed recovery code attempts")
            elif now >= expires_at:
                # Cooldown expired, remove it
                del self._cooldowns[user.id]

        # Hash the input code
        code_hash = hashlib.sha256(code.encode()).digest()

        async with self._sessionmaker() as session:
            # Look for matching code that hasn't been consumed
            row = await session.scalar(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.code_hash == code_hash,
                    RecoveryCode.consumed_at.is_(None),
                )
            )

            if row is None:
                # Wrong code or already consumed; record failure
                if user.id in self._cooldowns:
                    expires_at, fail_count = self._cooldowns[user.id]
                    fail_count += 1
                else:
                    fail_count = 1
                    expires_at = now + 60  # 60 second cooldown

                self._cooldowns[user.id] = (expires_at, fail_count)

                if fail_count >= 3:
                    raise RecoveryCooldown("Too many failed recovery code attempts")

                return False

            # Valid code, mark as consumed
            row.consumed_at = datetime.now(timezone.utc)
            await session.commit()

            # Clear cooldown on success
            if user.id in self._cooldowns:
                del self._cooldowns[user.id]

            return True

    async def mark_viewed(self, user: User) -> None:
        """Mark all unconsumed recovery codes as viewed by user.

        Args:
            user: User marking codes as viewed.
        """
        from server.app.models.recovery_code import RecoveryCode

        async with self._sessionmaker() as session:
            await session.execute(
                update(RecoveryCode)
                .where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.consumed_at.is_(None),
                )
                .values(viewed_at=datetime.now(timezone.utc))
            )
            await session.commit()

    async def list_status(self, user: User) -> RecoveryStatus:
        """Get status of recovery codes for user.

        Args:
            user: User to get status for.

        Returns:
            RecoveryStatus with total, consumed, remaining, and viewed counts.
        """
        from server.app.models.recovery_code import RecoveryCode

        async with self._sessionmaker() as session:
            # Total codes
            total_count = await session.scalar(
                select(func.count(RecoveryCode.id)).where(RecoveryCode.user_id == user.id)
            )

            # Consumed codes
            consumed_count = await session.scalar(
                select(func.count(RecoveryCode.id)).where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.consumed_at.isnot(None),
                )
            )

            # Check if any are viewed
            viewed = (
                await session.scalar(
                    select(RecoveryCode).where(
                        RecoveryCode.user_id == user.id,
                        RecoveryCode.viewed_at.isnot(None),
                    )
                )
                is not None
            )

        remaining = (total_count or 0) - (consumed_count or 0)
        return RecoveryStatus(
            total=total_count or 0, consumed=consumed_count or 0, remaining=remaining, viewed=viewed
        )
