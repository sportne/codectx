"""Canonical source span coordinates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    """Canonical source range.

    Byte offsets are canonical. Line/column values are display conveniences.
    Lines are 1-based. Columns are 0-based UTF-8 byte columns for MVP.
    """

    file_path: str
    start_byte: int
    end_byte: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def contains_line(self, line: int) -> bool:
        """Return whether the span includes a 1-based source line."""
        return self.start_line <= line <= self.end_line
