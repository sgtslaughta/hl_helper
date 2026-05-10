import pytest
from server.app.logs.categories import Category, CategoryRegistry, REGISTRY


def test_builtin_categories_present():
    names = REGISTRY.names()
    assert {"task", "inventory", "update", "cert", "transport", "posture", "system"}.issubset(names)


def test_register_adds():
    reg = CategoryRegistry()
    reg.register(Category("plugin.acme.scan", "ACME scanner runs", "info"))
    assert reg.get("plugin.acme.scan") is not None
    assert reg.get("plugin.acme.scan").description == "ACME scanner runs"


def test_duplicate_raises():
    reg = CategoryRegistry()
    reg.register(Category("x", "x", "info"))
    with pytest.raises(ValueError):
        reg.register(Category("x", "x dup", "info"))


def test_unknown_get_returns_none():
    reg = CategoryRegistry()
    assert reg.get("nope") is None


def test_all_returns_list_of_categories():
    reg = CategoryRegistry()
    reg.register(Category("a", "A", "info"))
    reg.register(Category("b", "B", "warn"))
    all_cats = reg.all()
    assert len(all_cats) == 2
    assert {c.name for c in all_cats} == {"a", "b"}
