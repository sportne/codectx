"""Scanner data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileRecord:
    """Metadata for one source file discovered by repository scanning."""

    path: str
    language: str | None
    content_hash: str
    size_bytes: int
    line_count: int
    is_test: bool = False
    is_generated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
