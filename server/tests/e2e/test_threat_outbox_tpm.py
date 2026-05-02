"""Threat-model E2E tests: outbox tamper detection and TPM fail-closed.

These tests shell out to Go test suite to confirm threat-model coverage.
Full implementation is on the agent side in Go.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not available")
def test_outbox_tamper_detected_on_replay() -> None:
    """Run Go outbox tamper detection tests.

    Tests TestVerify* and TestAck* patterns which verify cryptographic
    integrity and tamper detection in the outbox.
    """
    result = subprocess.run(
        ["go", "test", "-run", "TestVerify|TestAck", "./internal/outbox/..."],
        cwd="/home/user/code/hl_helper/agent",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not available")
def test_tpm_runtime_failure_fails_closed() -> None:
    """Run Go TPM keystore tests for fail-closed behavior.

    Tests that TPM-backed keystore operations fail safely under error
    conditions and do not leak or corrupt cryptographic material.
    """
    result = subprocess.run(
        ["go", "test", "-run", "TestTPM", "./internal/keystore/..."],
        cwd="/home/user/code/hl_helper/agent",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
