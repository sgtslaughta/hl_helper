"""Guard against scope_hash drift between production and migration impls.

The bootstrap-admin migration (0013) duplicates the `compute_scope_hash`
helper inline so it has no ORM/runtime dependency. If the production
implementation ever changes (e.g., new canonicalization rules), bindings
seeded by the migration would silently mismatch bindings created by the
API. This test asserts both implementations produce identical output for
representative inputs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable

from server.app.api.v1.bindings import compute_scope_hash as api_hash


def _load_migration_hash() -> Callable[[str, dict[str, Any]], str]:
    """Import the migration module's _compute_scope_hash without running upgrade()."""
    path = (
        Path(__file__).parent.parent.parent
        / "app"
        / "migrations"
        / "versions"
        / "0013_seed_bootstrap_admin.py"
    )
    spec = importlib.util.spec_from_file_location("_mig0013", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._compute_scope_hash  # type: ignore[attr-defined]


def test_global_scope_hash_matches() -> None:
    """global scope with empty value hashes identically in both impls."""
    mig_hash = _load_migration_hash()
    assert mig_hash("global", {}) == api_hash("global", {})


def test_group_scope_hash_matches() -> None:
    """group scope with group_id hashes identically."""
    mig_hash = _load_migration_hash()
    val: dict[str, object] = {"group_id": "g-prod-123"}
    assert mig_hash("group", val) == api_hash("group", val)


def test_host_list_scope_hash_matches() -> None:
    """host_list scope with multiple host_ids hashes identically."""
    mig_hash = _load_migration_hash()
    val: dict[str, object] = {"host_ids": ["h-1", "h-2", "h-3"]}
    assert mig_hash("host_list", val) == api_hash("host_list", val)


def test_nested_value_canonicalization_matches() -> None:
    """Nested dict value canonicalizes the same in both impls."""
    mig_hash = _load_migration_hash()
    val: dict[str, object] = {"a": {"b": 1, "c": [2, 3]}, "z": "trail"}
    assert mig_hash("custom", val) == api_hash("custom", val)
