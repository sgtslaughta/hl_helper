"""RBAC scope evaluator.

A Scope describes the set of resources a binding applies to. Scope.covers(r)
returns True iff r falls inside the scope.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Literal


ScopeKind = Literal["global", "group", "tag", "host_list", "self"]


@dataclass(frozen=True)
class Resource:
    """Resource a permission check is being made against.

    For collection-level checks (e.g. listing hosts), pass an empty resource —
    only `global` scope covers an empty resource.
    """
    id: str | None = None
    kind: str | None = None
    group_ids: frozenset[str] = field(default_factory=frozenset)  # all groups + ancestors of resource
    tags: frozenset[tuple[str, str]] = field(default_factory=frozenset)  # (key, value) pairs
    owner_user_id: str | None = None  # for "self" scope


@dataclass(frozen=True)
class Scope:
    kind: ScopeKind
    value: dict[str, object]  # opaque shape per kind

    def covers(
        self,
        resource: Resource,
        *,
        descendants_of: Callable[[str], frozenset[str]] | None = None,
    ) -> bool:
        """Return True iff `resource` lies inside this scope.

        descendants_of: callable that returns the set of all descendant group ids
        of a given group (inclusive of the group itself). Required for `group`
        scope; ignored otherwise.
        """
        if self.kind == "global":
            return True
        if self.kind == "group":
            target = self.value.get("group_id")
            if target is None or descendants_of is None:
                return False
            allowed = descendants_of(str(target))
            return bool(resource.group_ids & allowed)
        if self.kind == "tag":
            key = self.value.get("key")
            val = self.value.get("value")
            if key is None or val is None:
                return False
            return (key, val) in resource.tags
        if self.kind == "host_list":
            raw_ids = self.value.get("host_ids", [])
            ids: set[str] = set(raw_ids) if isinstance(raw_ids, list) else set()
            return resource.id in ids if resource.id else False
        if self.kind == "self":
            principal_id = self.value.get("principal_id")
            return resource.owner_user_id == principal_id and principal_id is not None
        return False
