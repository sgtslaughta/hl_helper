from server.app.rbac.scope import Scope, Resource


def desc(group_id: str) -> frozenset[str]:
    """Hierarchy: prod → prod.web, prod.db; staging."""
    if group_id == "prod":
        return frozenset({"prod", "prod.web", "prod.db"})
    if group_id == "prod.web":
        return frozenset({"prod.web"})
    if group_id == "staging":
        return frozenset({"staging"})
    return frozenset({group_id})


def test_global_scope_covers_anything():
    s = Scope(kind="global", value={})
    assert s.covers(Resource(id="h-1")) is True
    assert s.covers(Resource()) is True


def test_group_scope_descends():
    s = Scope(kind="group", value={"group_id": "prod"})
    res = Resource(id="h-1", group_ids=frozenset({"prod.web"}))
    assert s.covers(res, descendants_of=desc) is True

def test_group_scope_excludes_sibling():
    s = Scope(kind="group", value={"group_id": "staging"})
    res = Resource(id="h-1", group_ids=frozenset({"prod.web"}))
    assert s.covers(res, descendants_of=desc) is False

def test_group_scope_requires_descendants_of():
    s = Scope(kind="group", value={"group_id": "prod"})
    res = Resource(id="h-1", group_ids=frozenset({"prod"}))
    assert s.covers(res) is False  # without resolver

def test_tag_scope_match():
    s = Scope(kind="tag", value={"key": "env", "value": "prod"})
    res = Resource(id="h-1", tags=frozenset({("env", "prod")}))
    assert s.covers(res) is True

def test_tag_scope_mismatch():
    s = Scope(kind="tag", value={"key": "env", "value": "prod"})
    res = Resource(id="h-1", tags=frozenset({("env", "staging")}))
    assert s.covers(res) is False

def test_host_list_scope():
    s = Scope(kind="host_list", value={"host_ids": ["h-1", "h-2"]})
    assert s.covers(Resource(id="h-1")) is True
    assert s.covers(Resource(id="h-3")) is False

def test_self_scope():
    s = Scope(kind="self", value={"principal_id": "u-1"})
    assert s.covers(Resource(owner_user_id="u-1")) is True
    assert s.covers(Resource(owner_user_id="u-2")) is False

def test_unknown_kind_denies():
    s = Scope(kind="bogus", value={})
    assert s.covers(Resource(id="h-1")) is False
