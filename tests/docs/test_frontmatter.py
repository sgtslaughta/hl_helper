"""Verify every doc page has required frontmatter."""
from pathlib import Path
import pytest
import yaml

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"
REQUIRED = {"title", "status"}
ALLOWED_STATUS = {"stable", "partial", "planned"}
EXEMPT_DIRS = {"superpowers"}
# Auto-generated API docs are emitted by scripts/gen-docs.sh and don't carry
# our frontmatter. Hand-curated index.md stubs in those dirs DO carry it.
AUTOGEN_API_PARENTS = {"agent", "grpc", "python"}


def is_autogen(p: Path) -> bool:
    rel = p.relative_to(DOCS_ROOT)
    parts = rel.parts
    if len(parts) >= 4 and parts[0] == "developer" and parts[1] == "api" \
            and parts[2] in AUTOGEN_API_PARENTS and parts[-1] != "index.md":
        return True
    return False


def iter_pages():
    for p in DOCS_ROOT.rglob("*.md"):
        if any(part in EXEMPT_DIRS for part in p.relative_to(DOCS_ROOT).parts):
            continue
        if is_autogen(p):
            continue
        yield p


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    return yaml.safe_load(text[4:end]) or {}


@pytest.mark.parametrize("page", list(iter_pages()), ids=lambda p: str(p.relative_to(DOCS_ROOT)))
def test_required_frontmatter(page):
    fm = parse_frontmatter(page)
    missing = REQUIRED - fm.keys()
    assert not missing, f"{page}: missing {missing}"
    assert fm["status"] in ALLOWED_STATUS, f"{page}: status={fm.get('status')!r} not in {ALLOWED_STATUS}"
