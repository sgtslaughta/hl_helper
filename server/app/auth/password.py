from __future__ import annotations

import logging
import re
import string
from typing import Callable

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

logger = logging.getLogger(__name__)

"""
Password security module: argon2-cffi hashing + stdlib-based complexity checks.
Complexity validation uses length + char class diversity rather than zxcvbn.
HIBP check uses k-anonymity (5-char prefix sent).
"""


class PasswordHasher:
    def __init__(
        self,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
    ) -> None:
        self.time_cost = time_cost
        self.memory_cost = memory_cost
        self.parallelism = parallelism
        self._hasher = Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, stored: str, password: str) -> bool:
        try:
            self._hasher.verify(stored, password)
            return True
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            return False

    def needs_rehash(self, stored: str) -> bool:
        return self._hasher.check_needs_rehash(stored)


def validate_password(
    password: str,
    user_context: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []

    if len(password) < 12:
        errors.append("too_short")

    upper = bool(re.search(r"[A-Z]", password))
    lower = bool(re.search(r"[a-z]", password))
    digit = bool(re.search(r"\d", password))
    symbol = bool(re.search(rf"[{re.escape(string.punctuation)}]", password))

    char_classes = sum([upper, lower, digit, symbol])
    if char_classes < 3:
        errors.append("low_complexity")

    if user_context:
        password_lower = password.lower()
        for _key, value in user_context.items():
            if not value:
                continue
            tokens = re.split(r"[@.+\s_-]+", value.lower())
            for tok in (value.lower(), *tokens):
                if len(tok) >= 3 and tok in password_lower:
                    errors.append("contains_user_info")
                    break
            else:
                continue
            break

    return errors


def check_hibp(
    pw_sha1_hex: str,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> bool:
    if fetch is None:
        return False

    prefix = pw_sha1_hex[:5]
    try:
        response = fetch(prefix)
        suffix = pw_sha1_hex[5:].upper()
        for line in response.decode("utf-8").splitlines():
            if ":" in line:
                hash_suffix, count = line.split(":", 1)
                if hash_suffix == suffix:
                    return True
    except Exception as e:
        logger.warning(f"HIBP check failed: {e}")
        return False

    return False
