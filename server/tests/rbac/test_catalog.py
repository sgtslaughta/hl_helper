from server.app.rbac.catalog import Catalog, CATALOG


def test_catalog_is_canonical():
    cat = Catalog.load()
    assert "host:read" in cat.permissions
    assert cat.category("host:reboot") == "power"
    assert cat.is_high_risk("host:reboot") is True
    assert cat.is_high_risk("host:read") is False


def test_catalog_versioned():
    assert Catalog.VERSION == 1


def test_catalog_no_duplicates():
    names = [p.name for p in CATALOG]
    assert len(names) == len(set(names))


def test_known_high_risk_set():
    cat = Catalog.load()
    must_be_high = {"host:exec", "host:reboot", "host:shutdown", "host:revoke",
                    "host:terminal", "task:approve", "update:approve",
                    "container:exec", "secret:write", "secret:rotate",
                    "plugin:install", "user:impersonate", "role:write",
                    "setting:write", "session:terminate"}
    for p in must_be_high:
        assert cat.is_high_risk(p), f"{p} should be high_risk"


def test_categories_present():
    cats = {p.category for p in CATALOG}
    expected = {"host", "power", "group", "task", "update", "container", "secret",
                "plugin", "user", "role", "audit", "setting", "notification",
                "webhook", "session", "integration", "events"}
    assert expected <= cats
