"""Stdlib tracemalloc-based smoke tests for memory stability (fallback when memray unavailable)."""

from __future__ import annotations

import gc
import tracemalloc
from pathlib import Path

from server.app.audit.chain import AuditChain
from server.app.crypto.signing import FileBackend


def test_repeated_audit_append_does_not_grow(tmp_path: Path) -> None:
    """Audit chain repeated append: warm-up, then measure growth; ensure stable."""
    tracemalloc.start()
    backend = FileBackend.bootstrap(tmp_path / "signing")
    chain = AuditChain(backend, checkpoint_interval=100)

    # Warm-up: append 100 entries
    for i in range(100):
        chain.append(
            actor=f"warm-{i}",
            action="auth.warmup",
        )

    gc.collect()
    snap1 = tracemalloc.take_snapshot()

    # Measurement: append another 100 entries (same workload)
    for i in range(100, 200):
        chain.append(
            actor=f"measure-{i}",
            action="auth.measure",
        )

    gc.collect()
    snap2 = tracemalloc.take_snapshot()

    # Compute difference
    diff = snap2.compare_to(snap1, "lineno")
    growth = sum(s.size_diff for s in diff if s.size_diff > 0)

    # Allow for small constant overhead, but flag unbounded growth.
    # After GC and stable operations, growth should be under 1 MB.
    assert (
        growth < 1_000_000
    ), f"audit append leaked {growth} bytes; growth should be < 1 MB after warm-up"

    tracemalloc.stop()
    chain.verify()
