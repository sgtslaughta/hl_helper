from __future__ import annotations

import time
from dataclasses import dataclass

"""
Account lockout with escalating cooldowns: 5 fails/5min → 1m cooldown;
next fail → 5m cooldown. In-memory dict; DB persistence is TODO.
"""


@dataclass
class LockState:
    failure_count: int = 0
    last_failure_time: float | None = None
    lockout_expires_at: float | None = None
    lockout_level: int = 0


class LockoutTracker:
    def __init__(self) -> None:
        self._states: dict[str, LockState] = {}

    def record_failure(self, key: str) -> LockState:
        now = time.time()
        state = self._states.get(key, LockState())

        if state.lockout_expires_at and now < state.lockout_expires_at:
            self._states[key] = state
            return state

        was_locked = state.lockout_expires_at is not None

        # Reset failure count if last failure was outside 5-minute window
        if state.last_failure_time is not None and (now - state.last_failure_time) > 300:
            state.failure_count = 0

        state.failure_count += 1
        state.last_failure_time = now

        if state.failure_count >= 5 or was_locked:
            if was_locked:
                state.lockout_level += 1
                state.failure_count = 1
            else:
                state.lockout_level = 1

            cooldown = self._cooldown_for_level(state.lockout_level)
            state.lockout_expires_at = now + cooldown

        self._states[key] = state
        return state

    def record_success(self, key: str) -> None:
        if key in self._states:
            self._states[key] = LockState()

    def is_locked(self, key: str) -> bool:
        if key not in self._states:
            return False

        state = self._states[key]
        now = time.time()

        if state.lockout_expires_at is None:
            return False

        if now >= state.lockout_expires_at:
            self._states[key] = LockState()
            return False

        return True

    def _cooldown_for_level(self, level: int) -> int:
        if level == 1:
            return 60
        return 300
