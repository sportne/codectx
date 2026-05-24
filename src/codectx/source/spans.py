"""Canonical source span coordinates."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
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


def line_start_offsets(content: bytes) -> tuple[int, ...]:
    """Return 0-based byte offsets where each non-empty source line starts."""
    if not content:
        return ()

    starts = [0]
    for offset, byte in enumerate(content):
        if byte == 0x0A and offset + 1 < len(content):
            starts.append(offset + 1)
    return tuple(starts)


def line_count(content: bytes) -> int:
    """Return the number of source lines represented by content bytes."""
    return len(line_start_offsets(content))


def byte_to_line_col(
    line_starts: Sequence[int], byte_offset: int, *, content_length: int | None = None
) -> tuple[int, int]:
    """Convert a byte offset to a 1-based line and 0-based byte column."""
    if byte_offset < 0:
        raise ValueError("byte_offset must be non-negative")
    if content_length is not None and byte_offset > content_length:
        raise ValueError("byte_offset must not exceed content length")
    if not line_starts:
        raise ValueError("line_starts must not be empty")

    line_index = bisect_right(line_starts, byte_offset) - 1
    if line_index < 0:
        raise ValueError("byte_offset precedes first line start")
    return line_index + 1, byte_offset - line_starts[line_index]


def byte_range_to_span(
    file_path: str, content: bytes, start_byte: int, end_byte: int
) -> SourceSpan:
    """Build a SourceSpan for an exclusive byte range in content."""
    if start_byte < 0 or end_byte < start_byte or end_byte > len(content):
        raise ValueError("byte range must be within content bounds")

    starts = line_start_offsets(content)
    start_line, start_col = byte_to_line_col(
        starts, start_byte, content_length=len(content)
    )
    if end_byte == start_byte:
        end_line, end_col = start_line, start_col
    else:
        end_line, _ = byte_to_line_col(
            starts, end_byte - 1, content_length=len(content)
        )
        end_col = end_byte - starts[end_line - 1]
    return SourceSpan(
        file_path=file_path,
        start_byte=start_byte,
        end_byte=end_byte,
        start_line=start_line,
        start_col=start_col,
        end_line=end_line,
        end_col=end_col,
    )


def line_range_to_byte_range(
    content: bytes, start_line: int, end_line: int
) -> tuple[int, int]:
    """Convert an inclusive 1-based line range to an exclusive byte range."""
    starts = line_start_offsets(content)
    if start_line < 1 or end_line < start_line or end_line > len(starts):
        raise ValueError("line range must be within content bounds")

    start_byte = starts[start_line - 1]
    end_byte = starts[end_line] if end_line < len(starts) else len(content)
    return start_byte, end_byte
