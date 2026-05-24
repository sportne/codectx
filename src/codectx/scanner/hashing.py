"""Content hashing helpers for scanned source files."""

from __future__ import annotations

import hashlib
from pathlib import Path


def content_sha256(content: bytes) -> str:
    """Return the SHA-256 hex digest for content bytes."""
    return hashlib.sha256(content).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 hex digest for a file."""
    return content_sha256(Path(path).read_bytes())
