from server.app.logs.redact import redact


def test_redacts_bearer_token():
    doc = {"details": {"raw": "Authorization: Bearer abc.def-123_xyz"}}
    out = redact(doc)
    assert "abc.def-123_xyz" not in str(out)
    assert "«redacted:bearer»" in str(out)


def test_redacts_password_query():
    doc = {"message": "got url ?user=u&password=hunter2 done"}
    out = redact(doc)
    assert "hunter2" not in str(out)
    assert "«redacted:password»" in str(out)


def test_redacts_aws_access_key():
    doc = {"details": {"env": "AKIAIOSFODNN7EXAMPLE"}}
    out = redact(doc)
    assert "AKIAIOSFODNN7EXAMPLE" not in str(out)
    assert "«redacted:aws_access_key»" in str(out)


def test_redacts_api_key_case_insensitive():
    doc = {"details": {"raw": "API_KEY=secret_value_123"}}
    out = redact(doc)
    assert "secret_value_123" not in str(out)


def test_recursion_into_lists():
    doc = {"details": {"items": [{"token": "Bearer xyz123"}, {"safe": "ok"}]}}
    out = redact(doc)
    assert "xyz123" not in str(out)
    assert "ok" in str(out)


def test_preserves_benign_strings():
    doc = {"message": "shell_exec rc=0 in 1.8s", "details": {"k": "v"}}
    out = redact(doc)
    assert out["message"] == "shell_exec rc=0 in 1.8s"
    assert out["details"] == {"k": "v"}


def test_input_not_mutated():
    doc = {"details": {"raw": "Bearer abc"}}
    snapshot = str(doc)
    redact(doc)
    assert str(doc) == snapshot   # original unchanged


def test_plugin_redactor_applied():
    def plugin(s: str) -> str:
        return s.replace("CANARY_SECRET", "«redacted:canary»")
    doc = {"message": "leaked CANARY_SECRET here"}
    out = redact(doc, plugin_redactors=[plugin])
    assert "CANARY_SECRET" not in str(out)
    assert "«redacted:canary»" in str(out)


def test_redacts_private_key_block():
    doc = {"details": {"key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAtest\n-----END RSA PRIVATE KEY-----"}}
    out = redact(doc)
    assert "MIIEowIBAAKCAQEAtest" not in str(out)
    assert "«redacted:private_key»" in str(out)
