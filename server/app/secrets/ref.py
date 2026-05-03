"""SecretRef URI parser and dataclass."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SecretRef:
    """Reference to a secret with backend, path, and optional field selector."""

    backend: str
    path: str
    field: str | None = None

    @classmethod
    def parse(cls, uri: str) -> SecretRef:
        """Parse URI in format secret://<backend>/<path>[#<field>].

        Args:
            uri: URI string to parse

        Returns:
            SecretRef instance

        Raises:
            ValueError: If URI is malformed or contains path traversal attempts
        """
        parsed = urlparse(uri)

        if parsed.scheme != "secret":
            raise ValueError(f"Invalid scheme; expected 'secret://', got '{parsed.scheme}://'")

        if not parsed.netloc:
            raise ValueError("Missing backend in URI")

        backend = parsed.netloc
        path = parsed.path.lstrip("/")

        if not path:
            raise ValueError("Missing path in URI")

        # Validate path for traversal attacks
        if parsed.path.startswith("//"):
            raise ValueError("Invalid path: path traversal detected (leading slash)")

        # Check for .. segments
        segments = path.split("/")
        if ".." in segments or "." in segments:
            raise ValueError("Invalid path: path traversal detected (.. or . segments)")

        # Check for empty segments (double slash)
        if any(seg == "" for seg in segments):
            raise ValueError("Invalid path: path traversal detected (empty segments)")

        # Check for percent-encoded traversal patterns (%2e, %2f case-insensitive)
        if re.search(r"%2[ef]", path, re.IGNORECASE):
            raise ValueError("Invalid path: path traversal detected (percent-encoded)")

        field = parsed.fragment if parsed.fragment else None

        return cls(backend=backend, path=path, field=field)

    def __str__(self) -> str:
        """Encode as URI string for roundtrip."""
        uri = f"secret://{self.backend}/{self.path}"
        if self.field:
            uri += f"#{self.field}"
        return uri
