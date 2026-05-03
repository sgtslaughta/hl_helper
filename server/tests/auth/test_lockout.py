from __future__ import annotations

from freezegun import freeze_time

from server.app.auth.lockout import LockoutTracker


class TestLockoutTracker:
    def test_no_failures_not_locked(self) -> None:
        tracker = LockoutTracker()
        assert not tracker.is_locked("user:123")

    @freeze_time("2026-05-03 12:00:00")
    def test_five_failures_in_five_minutes_triggers_lockout(self) -> None:
        tracker = LockoutTracker()
        key = "user:123"

        for i in range(5):
            tracker.record_failure(key)

        assert tracker.is_locked(key)

    @freeze_time("2026-05-03 12:00:00")
    def test_lockout_lasts_one_minute(self) -> None:
        tracker = LockoutTracker()
        key = "user:123"

        for _ in range(5):
            tracker.record_failure(key)

        assert tracker.is_locked(key)

        with freeze_time("2026-05-03 12:01:00"):
            assert not tracker.is_locked(key)

    @freeze_time("2026-05-03 12:00:00")
    def test_sixth_failure_after_cooldown_escalates(self) -> None:
        tracker = LockoutTracker()
        key = "user:123"

        for _ in range(5):
            tracker.record_failure(key)

        with freeze_time("2026-05-03 12:01:30"):
            tracker.record_failure(key)
            assert tracker.is_locked(key)

        with freeze_time("2026-05-03 12:05:00"):
            assert tracker.is_locked(key)

        with freeze_time("2026-05-03 12:06:30"):
            assert not tracker.is_locked(key)

    @freeze_time("2026-05-03 12:00:00")
    def test_success_resets_counter(self) -> None:
        tracker = LockoutTracker()
        key = "user:123"

        for _ in range(4):
            tracker.record_failure(key)

        tracker.record_success(key)

        for _ in range(5):
            tracker.record_failure(key)

        assert tracker.is_locked(key)

    @freeze_time("2026-05-03 12:00:00")
    def test_different_keys_independent(self) -> None:
        tracker = LockoutTracker()
        key1 = "user:123"
        key2 = "user:456"

        for _ in range(5):
            tracker.record_failure(key1)

        assert tracker.is_locked(key1)
        assert not tracker.is_locked(key2)

    @freeze_time("2026-05-03 12:00:00")
    def test_sliding_window_resets_after_5min(self) -> None:
        tracker = LockoutTracker()
        key = "user:123"

        for _ in range(3):
            tracker.record_failure(key)

        with freeze_time("2026-05-03 12:05:01"):
            # More than 5 minutes passed, window resets
            tracker.record_failure(key)
            # Should be at count 1, not 4
            state = tracker._states[key]
            assert state.failure_count == 1

        with freeze_time("2026-05-03 12:05:02"):
            for _ in range(4):
                tracker.record_failure(key)
            assert tracker.is_locked(key)

    @freeze_time("2026-05-03 12:00:00")
    def test_failure_while_locked_does_not_extend_cooldown(self) -> None:
        tracker = LockoutTracker()
        key = "user:123"

        for _ in range(5):
            tracker.record_failure(key)

        state = tracker._states[key]
        original_lockout_expires_at = state.lockout_expires_at

        with freeze_time("2026-05-03 12:00:30"):
            tracker.record_failure(key)
            state = tracker._states[key]
            # Lockout time should not have extended
            assert state.lockout_expires_at == original_lockout_expires_at
