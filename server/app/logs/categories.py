"""Log category registry for built-in and plugin categories."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """A log category with name, description, and default level."""

    name: str
    description: str
    default_level: str


class CategoryRegistry:
    """Registry holding built-in and plugin log categories."""

    def __init__(self) -> None:
        """Initialize with empty registry."""
        self._categories: dict[str, Category] = {}

    def register(self, c: Category, *, source: str = "plugin") -> None:
        """Register a category.

        Args:
            c: Category to register.
            source: Source label (default: "plugin").

        Raises:
            ValueError: If category name already registered.
        """
        if c.name in self._categories:
            raise ValueError(f"Category '{c.name}' already registered")
        self._categories[c.name] = c

    def get(self, name: str) -> Category | None:
        """Get category by name.

        Args:
            name: Category name.

        Returns:
            Category if found, None otherwise.
        """
        return self._categories.get(name)

    def all(self) -> list[Category]:
        """Get all registered categories as a list.

        Returns:
            List of all categories.
        """
        return list(self._categories.values())

    def names(self) -> set[str]:
        """Get all registered category names.

        Returns:
            Set of category names.
        """
        return set(self._categories.keys())


# Module-level built-in registry
REGISTRY = CategoryRegistry()

# Register built-in categories
_builtin_categories = [
    Category("task", "Task execution and lifecycle", "info"),
    Category("inventory", "Inventory collection and updates", "info"),
    Category("update", "System and package updates", "info"),
    Category("cert", "Certificate lifecycle and validation", "info"),
    Category("transport", "Network transport and connectivity", "info"),
    Category("posture", "Security posture assessment", "info"),
    Category("system", "System-level events and diagnostics", "info"),
]

for cat in _builtin_categories:
    REGISTRY.register(cat, source="builtin")
