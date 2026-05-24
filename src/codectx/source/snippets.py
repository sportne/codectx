"""Source snippet extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass

from codectx.source.spans import (
    byte_range_to_span,
    line_count,
    line_range_to_byte_range,
)
from codectx.source.tokens import estimate_token_count


@dataclass(frozen=True)
class SourceSnippet:
    """Extracted source text with source coordinates."""

    file_path: str
    text: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    token_estimate: int


def snippet_by_byte_span(
    file_path: str,
    content: str | bytes,
    start_byte: int,
    end_byte: int,
    *,
    context_lines: int = 0,
) -> SourceSnippet:
    """Extract a snippet by exclusive byte range."""
    content_bytes = _content_bytes(content)
    if context_lines < 0:
        raise ValueError("context_lines must be non-negative")

    span = byte_range_to_span(file_path, content_bytes, start_byte, end_byte)
    if context_lines == 0:
        text = content_bytes[start_byte:end_byte].decode("utf-8")
        return SourceSnippet(
            file_path=file_path,
            text=text,
            start_line=span.start_line,
            end_line=span.end_line,
            start_byte=start_byte,
            end_byte=end_byte,
            token_estimate=estimate_token_count(text),
        )

    return snippet_by_line_range(
        file_path,
        content_bytes,
        span.start_line,
        span.end_line,
        context_lines=context_lines,
    )


def snippet_by_line_range(
    file_path: str,
    content: str | bytes,
    start_line: int,
    end_line: int,
    *,
    context_lines: int = 0,
) -> SourceSnippet:
    """Extract a snippet by inclusive 1-based line range."""
    content_bytes = _content_bytes(content)
    if context_lines < 0:
        raise ValueError("context_lines must be non-negative")

    total_lines = line_count(content_bytes)
    if start_line < 1 or end_line < start_line or end_line > total_lines:
        raise ValueError("line range must be within content bounds")

    actual_start_line = max(1, start_line - context_lines)
    actual_end_line = min(total_lines, end_line + context_lines)
    start_byte, end_byte = line_range_to_byte_range(
        content_bytes, actual_start_line, actual_end_line
    )
    text = content_bytes[start_byte:end_byte].decode("utf-8")
    return SourceSnippet(
        file_path=file_path,
        text=text,
        start_line=actual_start_line,
        end_line=actual_end_line,
        start_byte=start_byte,
        end_byte=end_byte,
        token_estimate=estimate_token_count(text),
    )


def _content_bytes(content: str | bytes) -> bytes:
    if isinstance(content, bytes):
        return content
    return content.encode("utf-8")
