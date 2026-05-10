"""Redaction engine for server-side log ingest."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from typing import Any

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----"), "«redacted:private_key»"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"), "«redacted:bearer»"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "«redacted:aws_access_key»"),
    (re.compile(r"(?i)api[_-]?key=([^\s&]+)"), "«redacted:api_key»"),
    (re.compile(r"password=([^\s&]+)"), "«redacted:password»"),
    (re.compile(r"token=([^\s&]+)"), "«redacted:token»"),
]


def _redact_str(s: str, plugin_redactors: list[Callable[[str], str]] | None) -> str:
    """Apply regex and plugin redactions to a single string."""
    for pat, repl in _PATTERNS:
        s = pat.sub(repl, s)
    if plugin_redactors:
        for fn in plugin_redactors:
            s = fn(s)
    return s


def _walk(obj: Any, plugin_redactors: list[Callable[[str], str]] | None) -> Any:
    """Recursively walk and redact an object tree."""
    if isinstance(obj, str):
        return _redact_str(obj, plugin_redactors)
    if isinstance(obj, dict):
        return {k: _walk(v, plugin_redactors) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, plugin_redactors) for v in obj]
    return obj


def redact(doc: dict, plugin_redactors: list[Callable[[str], str]] | None = None) -> dict:
    """Recursively replace secret-bearing substrings in string leaves with redaction markers.

    Args:
        doc: ECS event document (dict) to redact.
        plugin_redactors: Optional list of custom redactor functions applied after built-in patterns.
                         Each function takes a string and returns a redacted string.

    Returns:
        New dict with secrets redacted (does not mutate input).
    """
    return _walk(deepcopy(doc), plugin_redactors)
