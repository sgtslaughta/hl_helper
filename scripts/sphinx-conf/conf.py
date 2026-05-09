"""Sphinx config for autodoc → markdown export."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

project = "hl_helper"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx_markdown_builder"]
master_doc = "index"
exclude_patterns = ["_build"]
markdown_anchor_sections = True
