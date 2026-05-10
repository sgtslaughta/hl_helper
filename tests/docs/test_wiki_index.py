"""Verify wiki manifest schema once built. Skipped if missing."""
import json
from pathlib import Path
import pytest

MANIFEST = Path(__file__).resolve().parents[2] / "webui" / "public" / "wiki" / "index.json"


@pytest.mark.skipif(not MANIFEST.exists(), reason="wiki not built yet")
def test_manifest_schema():
    data = json.loads(MANIFEST.read_text())
    assert isinstance(data, dict)
    assert "pages" in data and isinstance(data["pages"], list)
    for entry in data["pages"]:
        assert {"path", "title", "headings"} <= entry.keys()
