"""TOTP MFA service — RFC 6238 compliant time-based one-time passwords."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import NamedTuple

import pyotp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.app.models import TotpSecret, User


class EnrollBeginOut(NamedTuple):
    """Output from enroll_begin()."""

    provisioning_uri: str
    secret_b32: str


class TotpService:
    """TOTP service for enrollment and verification."""

    class TotpCooldown(Exception):
        """Raised when user exceeds wrong attempt threshold."""

        pass

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        encryption_key: bytes | None = None,
    ) -> None:
        """Initialize TotpService.

        Args:
            sessionmaker: AsyncSession factory.
            encryption_key: 32-byte AES-GCM key. If None, encryption is disabled (dev only).
        """
        self.sessionmaker = sessionmaker
        self.encryption_key = encryption_key
        # In-memory cooldown tracker: user_id -> (count, first_attempt_time)
        self._cooldown_tracker: dict[str, tuple[int, datetime]] = {}

    async def enroll_begin(self, user: User) -> EnrollBeginOut:
        """Begin TOTP enrollment for a user.

        Generates a new secret, encrypts it, persists a TotpSecret row with
        confirmed_at=None, and returns the provisioning URI and secret in base32.
        If user already has an enrolled secret, it is replaced.

        Args:
            user: User to enroll.

        Returns:
            EnrollBeginOut with provisioning_uri and secret_b32.
        """
        # Generate new secret
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        # Encrypt secret
        ciphertext = self._encrypt(secret.encode())

        # Create TotpSecret row, replacing any existing one
        async with self.sessionmaker() as session:
            # Delete any existing secret for this user
            await session.execute(
                delete(TotpSecret).where(TotpSecret.user_id == user.id)
            )

            # Create new secret
            totp_secret = TotpSecret(
                user_id=user.id,
                secret_ciphertext=ciphertext,
                algorithm="sha1",
                digits=6,
                period_s=30,
                confirmed_at=None,
            )
            session.add(totp_secret)
            await session.commit()

        # Generate provisioning URI (email from user object)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="hl_helper",
        )

        return EnrollBeginOut(
            provisioning_uri=provisioning_uri,
            secret_b32=secret,
        )

    async def enroll_finish(self, user: User, code: str) -> bool:
        """Finish TOTP enrollment by verifying a code.

        If the code is valid for the current or adjacent step, sets confirmed_at
        to now and updates last_used_step.

        Args:
            user: User completing enrollment.
            code: 6-digit code to verify.

        Returns:
            True if code is valid and enrollment succeeds, False otherwise.
        """
        async with self.sessionmaker() as session:
            secret_record = await session.scalar(
                select(TotpSecret).where(TotpSecret.user_id == user.id)
            )
            if secret_record is None:
                self._track_failure(user)
                return False

            # Decrypt secret
            secret_bytes = self._decrypt(secret_record.secret_ciphertext)
            secret_str = secret_bytes.decode()

            # Verify code using pyotp with ±1 window
            totp = pyotp.TOTP(secret_str, interval=secret_record.period_s)
            now = datetime.now(timezone.utc)

            if totp.verify(code, valid_window=1):
                # Valid code found; fetch the matched step for tracking
                matched_step = totp.timecode(now)
                secret_record.confirmed_at = now
                secret_record.last_used_step = matched_step
                await session.commit()
                return True

            # Code did not match any valid step
            self._track_failure(user)
            return False

    async def verify(self, user: User, code: str) -> bool:
        """Verify a TOTP code for an authenticated user.

        Accepts the current step ± 1 window. Rejects replays (step must be
        > last_used_step). Updates last_used_step atomically.

        Args:
            user: User verifying.
            code: 6-digit code to verify.

        Returns:
            True if code is valid and not a replay, False otherwise.

        Raises:
            TotpCooldown: If user exceeds wrong attempt threshold.
        """
        # Check cooldown before attempting verification
        await self.cooldown_check(user)

        async with self.sessionmaker() as session:
            secret_record = await session.scalar(
                select(TotpSecret).where(TotpSecret.user_id == user.id)
            )
            if secret_record is None or secret_record.confirmed_at is None:
                self._track_failure(user)
                return False

            # Decrypt secret
            secret_bytes = self._decrypt(secret_record.secret_ciphertext)
            secret_str = secret_bytes.decode()

            # Verify code using pyotp with ±1 window
            totp = pyotp.TOTP(secret_str, interval=secret_record.period_s)
            now = datetime.now(timezone.utc)

            if totp.verify(code, valid_window=1):
                # Valid code found; fetch the matched step for replay detection
                matched_step = totp.timecode(now)

                # Check for replay (must be > last_used_step)
                if secret_record.last_used_step is not None:
                    if matched_step <= secret_record.last_used_step:
                        # Replay detected
                        self._track_failure(user)
                        return False

                # Valid code; update last_used_step
                secret_record.last_used_step = matched_step
                await session.commit()
                return True

            # Code did not match any valid step
            self._track_failure(user)
            return False

    async def cooldown_check(self, user: User) -> None:
        """Check if user exceeds wrong attempt cooldown threshold.

        If 5 wrong attempts within 60 seconds, raises TotpCooldown.

        Args:
            user: User to check.

        Raises:
            TotpCooldown: If threshold exceeded.
        """
        now = datetime.now(timezone.utc)

        if user.id in self._cooldown_tracker:
            count, first_attempt = self._cooldown_tracker[user.id]
            elapsed = (now - first_attempt).total_seconds()

            if elapsed < 60:
                if count >= 5:
                    raise self.TotpCooldown(
                        f"Too many failed attempts for user {user.id}"
                    )
            else:
                # Window expired; reset tracker
                del self._cooldown_tracker[user.id]

    def _track_failure(self, user: User) -> None:
        """Track a failed verification attempt for cooldown.

        Args:
            user: User with failed attempt.
        """
        now = datetime.now(timezone.utc)

        if user.id not in self._cooldown_tracker:
            self._cooldown_tracker[user.id] = (1, now)
        else:
            count, first_attempt = self._cooldown_tracker[user.id]
            elapsed = (now - first_attempt).total_seconds()

            if elapsed < 60:
                self._cooldown_tracker[user.id] = (count + 1, first_attempt)
            else:
                # Window expired; reset
                self._cooldown_tracker[user.id] = (1, now)

    def _encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt plaintext using AES-GCM.

        Random 12-byte nonce is prepended to ciphertext.

        Args:
            plaintext: Data to encrypt.

        Returns:
            nonce (12 bytes) + ciphertext.
        """
        if self.encryption_key is None:
            raise ValueError("Encryption key not configured")

        nonce = os.urandom(12)
        cipher = AESGCM(self.encryption_key)
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def _decrypt(self, ciphertext_with_nonce: bytes) -> bytes:
        """Decrypt ciphertext using AES-GCM.

        Expects: nonce (12 bytes) + ciphertext.

        Args:
            ciphertext_with_nonce: Encrypted data with prepended nonce.

        Returns:
            Decrypted plaintext.
        """
        if self.encryption_key is None:
            raise ValueError("Encryption key not configured")

        nonce = ciphertext_with_nonce[:12]
        ciphertext = ciphertext_with_nonce[12:]
        cipher = AESGCM(self.encryption_key)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
        return plaintext
