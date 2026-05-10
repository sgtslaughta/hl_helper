"""Crawl internal markdown links, fail on broken refs."""
import re
from pathlib import Path
import pytest

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


AUTOGEN_API_PARENTS = {"agent", "grpc", "python"}


def is_autogen(p: Path) -> bool:
    parts = p.relative_to(DOCS_ROOT).parts
    if len(parts) >= 4 and parts[0] == "developer" and parts[1] == "api" \
            and parts[2] in AUTOGEN_API_PARENTS and parts[-1] != "index.md":
        return True
    return False


def iter_pages():
    for p in DOCS_ROOT.rglob("*.md"):
        rel_parts = p.relative_to(DOCS_ROOT).parts
        if "superpowers" in rel_parts or "_planned" in rel_parts:
            continue
        if is_autogen(p):
            continue
        yield p


@pytest.mark.parametrize("page", list(iter_pages()), ids=lambda p: str(p.relative_to(DOCS_ROOT)))
def test_internal_links_resolve(page):
    text = page.read_text()
    bad = []
    for href in LINK_RE.findall(text):
        if href.startswith(("http://", "https://", "mailto:", "#", "<")):
            continue
        target = href.split("#", 1)[0]
        if not target:
            continue
        # Skip links into ignored dirs that may be absent on a clean checkout.
        if target.startswith(("../../superpowers/", "../superpowers/", "superpowers/")):
            continue
        resolved = (page.parent / target).resolve()
        if not resolved.exists():
            bad.append(href)
    assert not bad, f"{page}: broken {bad}"
