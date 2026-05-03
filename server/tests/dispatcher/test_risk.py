"""Tests for risk classification."""

from __future__ import annotations

from server.app.dispatcher.risk import classify


def test_shell_exec_always_high() -> None:
    """shell_exec always returns high."""
    assert classify("shell_exec", 1) == "high"
    assert classify("shell_exec", 100) == "high"


def test_reboot_one_host_med_many_high() -> None:
    """Reboot: 1 host=med, >1=high."""
    assert classify("reboot", 1) == "med"
    assert classify("reboot", 2) == "high"
    assert classify("reboot", 100) == "high"


def test_pkg_update_security_only_low() -> None:
    """pkg_update with classes=['security'] → low."""
    assert classify("pkg_update", 10, payload_metadata={"classes": ["security"]}) == "low"


def test_pkg_update_default_med() -> None:
    """pkg_update without security metadata → med."""
    assert classify("pkg_update", 5) == "med"
    assert classify("pkg_update", 5, payload_metadata={}) == "med"
    assert classify("pkg_update", 5, payload_metadata={"classes": ["minor"]}) == "med"


def test_unknown_payload_fail_closed_high() -> None:
    """Unknown payload type → high."""
    assert classify("unknown_type", 1) == "high"


def test_container_update_threshold_5() -> None:
    """container_update: <=5 hosts=med, >5=high."""
    assert classify("container_update", 1) == "med"
    assert classify("container_update", 5) == "med"
    assert classify("container_update", 6) == "high"
    assert classify("container_update", 100) == "high"
